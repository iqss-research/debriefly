"""Authenticated feedback form and email notification."""

from __future__ import annotations

import asyncio
import logging
from threading import Lock
import time

import reflex as rx

from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import User
from debriefly.reflex.local_auth import (
    PendingEmail,
    normalize_email,
    send_smtp_email,
)
from debriefly.reflex.template import template


logger = logging.getLogger(__name__)

FEEDBACK_RECIPIENT = "knakamura@g.harvard.edu"
FEEDBACK_EMAIL_SUBJECT = "New Debriefly feedback request"
FEEDBACK_PURPOSE = "feedback"
FEEDBACK_SUBJECT_MAX_LENGTH = 120
FEEDBACK_MESSAGE_MAX_LENGTH = 5_000
FEEDBACK_SEND_LIMIT = 5
FEEDBACK_SEND_WINDOW_SECONDS = 60 * 60

FEEDBACK_TYPES = {
    "general": "General feedback",
    "bug": "Bug report",
    "feature": "Feature request",
    "support": "Support request",
}

_feedback_attempts: dict[str, list[float]] = {}
_feedback_attempts_lock = Lock()


def _feedback_rate_limited(user_id: str, *, now: float | None = None) -> bool:
    """Limit notification attempts per signed-in account and backend process."""
    current = time.monotonic() if now is None else now
    cutoff = current - FEEDBACK_SEND_WINDOW_SECONDS
    with _feedback_attempts_lock:
        recent = [
            attempt
            for attempt in _feedback_attempts.get(user_id, [])
            if attempt > cutoff
        ]
        if len(recent) >= FEEDBACK_SEND_LIMIT:
            _feedback_attempts[user_id] = recent
            return True
        recent.append(current)
        _feedback_attempts[user_id] = recent
        return False


def _required_text(
    form_data: dict[str, str],
    key: str,
    label: str,
    max_length: int,
) -> str:
    value = form_data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"Enter a {label.lower()}.")
    value = value.strip()
    if not value:
        raise ValueError(f"Enter a {label.lower()}.")
    if len(value) > max_length:
        raise ValueError(f"{label} is too long.")
    return value


def _build_feedback_email(
    user: User,
    form_data: dict[str, str],
) -> PendingEmail:
    """Build a notification using only server-controlled email headers."""
    feedback_type = form_data.get("request_type", "")
    if not isinstance(feedback_type, str) or feedback_type not in FEEDBACK_TYPES:
        raise ValueError("Choose a valid request type.")

    subject = _required_text(
        form_data,
        "subject",
        "Subject",
        FEEDBACK_SUBJECT_MAX_LENGTH,
    )
    if "\r" in subject or "\n" in subject:
        raise ValueError("Subject must be one line.")
    message = _required_text(
        form_data,
        "message",
        "Request",
        FEEDBACK_MESSAGE_MAX_LENGTH,
    )

    try:
        account_email = normalize_email(user.email_normalized or "")
    except ValueError:
        account_email = "Unavailable"

    body = "\n".join(
        [
            "A signed-in Debriefly user submitted a request.",
            "",
            f"Request type: {FEEDBACK_TYPES[feedback_type]}",
            f"Account email: {account_email}",
            f"Account ID: {user.user_id}",
            "",
            "Subject:",
            subject,
            "",
            "Request:",
            message,
        ]
    )
    return PendingEmail(
        recipient=FEEDBACK_RECIPIENT,
        purpose=FEEDBACK_PURPOSE,
        subject=FEEDBACK_EMAIL_SUBJECT,
        body=body,
    )


async def _sync_feedback_user(state: "FeedbackState") -> bool:
    """Re-resolve the server-side login immediately before sending email."""
    return await state.sync_user_from_session()


class FeedbackState(MainState):
    request_type: str = "general"
    subject: str = ""
    message: str = ""
    sending: bool = False
    error: str = ""

    async def submit_feedback(self, form_data: dict[str, str]):
        """Validate and email one request from the authenticated account."""
        self.error = ""
        if not await _sync_feedback_user(self):
            self.error = "Please sign in before sending feedback."
            yield rx.toast.error(self.error)
            return

        try:
            pending = _build_feedback_email(self.user, form_data)
        except ValueError as exc:
            self.error = str(exc)
            yield rx.toast.error(self.error)
            return

        if _feedback_rate_limited(self.user_id):
            self.error = "Too many requests were sent. Please try again later."
            yield rx.toast.error(self.error)
            return

        self.sending = True
        yield
        try:
            sent = await asyncio.to_thread(send_smtp_email, pending)
        except Exception:
            logger.exception("Unexpected feedback email delivery failure")
            sent = False
        finally:
            self.sending = False

        if not sent:
            self.error = (
                "Your request could not be emailed. Please try again later or "
                "use GitHub Issues."
            )
            yield rx.toast.error(self.error)
            return

        self.request_type = "general"
        self.subject = ""
        self.message = ""
        yield rx.toast.success("Your request was sent to the Debriefly maintainer.")


@rx.page(route="/feedback", title="Feedback", on_load=[MainState.init])
@template
def feedback_page() -> rx.Component:
    """Render the authenticated feedback request form."""
    return rx.box(
        rx.vstack(
            rx.heading("Contact the Debriefly maintainer", size="6"),
            rx.text(
                "Send a bug report, feature request, support request, or other "
                "feedback. Your signed-in account email will be included so the "
                "maintainer can respond."
            ),
            rx.form.root(
                rx.vstack(
                    rx.vstack(
                        rx.text("Request type", weight="bold"),
                        rx.select.root(
                            rx.select.trigger(width="100%"),
                            rx.select.content(
                                *[
                                    rx.select.item(label, value=value)
                                    for value, label in FEEDBACK_TYPES.items()
                                ]
                            ),
                            name="request_type",
                            value=FeedbackState.request_type,
                            on_change=FeedbackState.set_request_type,
                            width="100%",
                        ),
                        align="start",
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Subject", weight="bold"),
                        rx.input(
                            name="subject",
                            value=FeedbackState.subject,
                            on_change=FeedbackState.set_subject,
                            max_length=FEEDBACK_SUBJECT_MAX_LENGTH,
                            required=True,
                            width="100%",
                        ),
                        align="start",
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Request", weight="bold"),
                        rx.text_area(
                            name="message",
                            value=FeedbackState.message,
                            on_change=FeedbackState.set_message,
                            max_length=FEEDBACK_MESSAGE_MAX_LENGTH,
                            required=True,
                            min_height="12rem",
                            resize="vertical",
                            width="100%",
                        ),
                        rx.text(
                            "Maximum 5,000 characters.",
                            color=rx.color("gray", 10),
                            size="1",
                        ),
                        align="start",
                        spacing="1",
                        width="100%",
                    ),
                    rx.cond(
                        FeedbackState.error != "",
                        rx.callout(
                            FeedbackState.error,
                            icon="triangle-alert",
                            color_scheme="red",
                            width="100%",
                        ),
                    ),
                    rx.button(
                        rx.cond(FeedbackState.sending, "Sending…", "Send request"),
                        type="submit",
                        color_scheme="green",
                        is_disabled=FeedbackState.sending,
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                on_submit=FeedbackState.submit_feedback,
                reset_on_submit=False,
                width="100%",
            ),
            rx.divider(),
            # rx.text("For public bug reports and code contributions:"),
            # rx.link(
            #    rx.button("Open GitHub Issues", variant="outline"),
            #    href="https://github.com/iqss-research/debriefly/issues",
            #    is_external=True,
            #    text_decoration="none",
            # ),
            # width="100%",
            # align_items="flex_start",
            # spacing="4",
        ),
        width="100%",
        max_width="48rem",
        margin="0 auto",
        padding="2em",
    )
