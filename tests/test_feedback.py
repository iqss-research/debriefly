import asyncio
import re

import pytest

import debriefly.reflex.local_auth as local_auth
import debriefly.reflex.pages.feedback as feedback
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import User


@pytest.fixture(autouse=True)
def reset_feedback_rate_limit():
    with feedback._feedback_attempts_lock:
        feedback._feedback_attempts.clear()
    yield
    with feedback._feedback_attempts_lock:
        feedback._feedback_attempts.clear()


def _user() -> User:
    return User(
        user_id="user_123",
        email_normalized="researcher@example.org",
    )


def _valid_form_data(**overrides) -> dict[str, str]:
    data = {
        "request_type": "feature",
        "subject": "Add a useful option",
        "message": "It would help our research workflow.",
    }
    data.update(overrides)
    return data


def _feedback_state() -> feedback.FeedbackState:
    parent = MainState(_reflex_internal_init=True)
    return feedback.FeedbackState(
        parent_state=parent,
        _reflex_internal_init=True,
    )


async def _run_submission(state, form_data):
    events = []
    async for event in feedback.FeedbackState.submit_feedback.fn(state, form_data):
        events.append(event)
    return events


def test_feedback_email_uses_fixed_headers_and_authenticated_account():
    pending = feedback._build_feedback_email(
        _user(),
        _valid_form_data(
            recipient="attacker@example.org",
            to="attacker@example.org",
            sender="attacker@example.org",
            subject="Please review this request",
        ),
    )

    assert pending.recipient == "knakamura@g.harvard.edu"
    assert pending.subject == "New Debriefly feedback request"
    assert pending.purpose == "feedback"
    assert "Account email: researcher@example.org" in pending.body
    assert "Account ID: user_123" in pending.body
    assert "Please review this request" in pending.body
    assert "attacker@example.org" not in pending.body


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"request_type": "forged"}, "Choose a valid request type."),
        ({"subject": "  "}, "Enter a subject."),
        ({"message": "  "}, "Enter a request."),
        (
            {"subject": "x" * (feedback.FEEDBACK_SUBJECT_MAX_LENGTH + 1)},
            "Subject is too long.",
        ),
        (
            {"message": "x" * (feedback.FEEDBACK_MESSAGE_MAX_LENGTH + 1)},
            "Request is too long.",
        ),
        ({"subject": "Safe\r\nBcc: attacker@example.org"}, "Subject must be one line."),
    ],
)
def test_feedback_email_rejects_invalid_input(overrides, error):
    with pytest.raises(ValueError, match=f"^{re.escape(error)}$"):
        feedback._build_feedback_email(_user(), _valid_form_data(**overrides))


def test_feedback_submission_success_clears_form(monkeypatch):
    captured = []

    async def authenticate(state):
        state._set_authenticated_user(_user())
        return True

    def send(message):
        captured.append(message)
        return True

    monkeypatch.setattr(feedback, "_sync_feedback_user", authenticate)
    monkeypatch.setattr(feedback, "send_smtp_email", send)
    state = _feedback_state()
    state.request_type = "feature"
    state.subject = "Add a useful option"
    state.message = "It would help our research workflow."

    events = asyncio.run(_run_submission(state, _valid_form_data()))

    assert len(captured) == 1
    assert captured[0].recipient == feedback.FEEDBACK_RECIPIENT
    assert len(events) == 2
    assert state.request_type == "general"
    assert state.subject == ""
    assert state.message == ""
    assert state.sending is False
    assert state.error == ""


def test_feedback_submission_failure_preserves_form(monkeypatch):
    async def authenticate(state):
        state._set_authenticated_user(_user())
        return True

    monkeypatch.setattr(feedback, "_sync_feedback_user", authenticate)
    monkeypatch.setattr(feedback, "send_smtp_email", lambda message: False)
    state = _feedback_state()
    state.request_type = "support"
    state.subject = "Please help"
    state.message = "The request should remain after an SMTP failure."

    events = asyncio.run(
        _run_submission(
            state,
            _valid_form_data(
                request_type="support",
                subject=state.subject,
                message=state.message,
            ),
        )
    )

    assert len(events) == 2
    assert state.request_type == "support"
    assert state.subject == "Please help"
    assert state.message == "The request should remain after an SMTP failure."
    assert state.sending is False
    assert "could not be emailed" in state.error
    assert "GitHub" not in state.error


def test_anonymous_feedback_is_not_sent(monkeypatch):
    sent = []

    async def anonymous(state):
        return False

    monkeypatch.setattr(feedback, "_sync_feedback_user", anonymous)
    monkeypatch.setattr(feedback, "send_smtp_email", sent.append)
    state = _feedback_state()

    events = asyncio.run(_run_submission(state, _valid_form_data()))

    assert sent == []
    assert len(events) == 1
    assert state.error == "Please sign in before sending feedback."


def test_feedback_rate_limit_is_per_authenticated_account():
    for second in range(feedback.FEEDBACK_SEND_LIMIT):
        assert not feedback._feedback_rate_limited("user-a", now=float(second))

    assert feedback._feedback_rate_limited("user-a", now=10.0)
    assert not feedback._feedback_rate_limited("user-b", now=10.0)
    assert not feedback._feedback_rate_limited(
        "user-a",
        now=float(feedback.FEEDBACK_SEND_WINDOW_SECONDS + 10),
    )


def test_feedback_page_renders_form_without_exposing_recipient():
    markup = str(feedback.feedback_page)

    assert "Send request" in markup
    assert "Open GitHub Issues" not in markup
    assert "github.com/iqss-research/debriefly" not in markup
    assert "mailto:" not in markup
    assert feedback.FEEDBACK_RECIPIENT not in markup


def test_smtp_transport_uses_existing_configuration(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.test", 587, 15)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def starttls(self, context):
            return None

        def login(self, username, password):
            assert (username, password) == ("resend", "secret")

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setenv("SMTP_SSL", "false")
    monkeypatch.setenv("SMTP_USERNAME", "resend")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "Debriefly <no-reply@example.org>")
    monkeypatch.setattr(local_auth.smtplib, "SMTP", FakeSMTP)

    assert local_auth.send_smtp_email(
        local_auth.PendingEmail(
            recipient=feedback.FEEDBACK_RECIPIENT,
            purpose="feedback",
            subject=feedback.FEEDBACK_EMAIL_SUBJECT,
            body="Plain-text feedback body",
        )
    )

    assert len(sent) == 1
    assert sent[0]["To"] == feedback.FEEDBACK_RECIPIENT
    assert sent[0]["Subject"] == feedback.FEEDBACK_EMAIL_SUBJECT
    assert sent[0].get_content().strip() == "Plain-text feedback body"
