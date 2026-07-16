"""Local account pages and native forms for HttpOnly-cookie authentication."""

from __future__ import annotations

import reflex as rx

from debriefly.reflex import styles
from debriefly.reflex.auth import (
    FORGOT_PASSWORD_ROUTE,
    REGISTER_ROUTE,
    RESET_PASSWORD_ROUTE,
    SIGN_IN_ROUTE,
    VERIFY_EMAIL_ROUTE,
)
from debriefly.reflex.local_auth import auth_api_endpoint, safe_relative_path


# These pages contain a one-time token in the URL and submit a native form.
# In local development that POST crosses from :3000 to :8000. `no-referrer`
# serializes the browser's Origin header as `null`, which correctly fails our
# CSRF check. `strict-origin` keeps the URL path/token private while preserving
# the origin needed by the backend.
_TOKEN_PAGE_META = [{"name": "referrer", "content": "strict-origin"}]


class AuthPageState(rx.State):
    alert_message: str = ""
    alert_is_error: bool = False
    next_path: str = "/"
    reset_token: str = ""

    def load(self):
        params = self.router.page.params or {}
        error = str(params.get("error", ""))
        notice = str(params.get("notice", ""))
        self.next_path = safe_relative_path(str(params.get("next", "/")))
        self.reset_token = str(params.get("token", ""))[:512]
        error_messages = {
            "invalid": (
                "The email or password is incorrect. If your account was migrated, "
                "use “Set up or reset password” below."
            ),
            "invalid-input": "Enter a valid email address.",
            "invalid-password": "Use matching passwords of at least 12 characters.",
            "password-match": "The passwords do not match.",
            "invalid-link": "This one-time link is invalid, expired, or already used.",
            "rate-limited": "Too many attempts. Please wait and try again.",
            "configuration": "Sign-in is temporarily unavailable. Please contact the administrator.",
            "email": "The verification email could not be sent. Please try again later.",
            "email-not-configured": (
                "Email delivery is not configured. Set SMTP_HOST and SMTP_FROM, "
                "or ask an administrator for a securely generated setup link."
            ),
            "disabled": "New account registration is currently disabled.",
        }
        notice_messages = {
            "check-email": (
                "Check your email for a link to verify your address and choose "
                "a password. Existing accounts are not disclosed."
            ),
            "password-email": "If that account exists, a one-time password link has been sent.",
            "verified": (
                "Your email is verified and your password is saved. You can sign in now."
            ),
            "password-updated": "Your password has been saved. All older sessions were revoked.",
            "signed-out": "You have been signed out.",
        }
        if error:
            self.alert_is_error = True
            self.alert_message = error_messages.get(
                error, "The request could not be completed."
            )
        elif notice:
            self.alert_is_error = False
            self.alert_message = notice_messages.get(
                notice, "The request was completed."
            )
        else:
            self.alert_is_error = False
            self.alert_message = ""


def _auth_input(
    label: str,
    name: str,
    *,
    type_: str = "text",
    autocomplete: str = "",
) -> rx.Component:
    return rx.vstack(
        rx.el.label(label, html_for=f"auth-{name}", size="2", weight="medium"),
        rx.el.input(
            id=f"auth-{name}",
            name=name,
            type=type_,
            auto_complete=autocomplete,
            required=True,
            width="100%",
            border=styles.border,
            border_radius=styles.border_radius,
            padding="0.65rem 0.75rem",
            background_color="white",
        ),
        align="start",
        spacing="1",
        width="100%",
    )


def _alert() -> rx.Component:
    return rx.cond(
        AuthPageState.alert_message != "",
        rx.cond(
            AuthPageState.alert_is_error,
            rx.callout(
                AuthPageState.alert_message,
                icon="triangle-alert",
                color_scheme="red",
                width="100%",
            ),
            rx.callout(
                AuthPageState.alert_message,
                icon="info",
                color_scheme="green",
                width="100%",
            ),
        ),
    )


def _auth_shell(
    title: str,
    description: str,
    content: rx.Component,
) -> rx.Component:
    return rx.theme(
        rx.center(
            rx.card(
                rx.vstack(
                    rx.heading(title, size="7", text_align="center"),
                    rx.text(
                        description,
                        color=styles.text_color,
                        text_align="center",
                        line_height="1.5",
                    ),
                    _alert(),
                    content,
                    rx.text(
                        "Authentication data is stored by Debriefly and used only to secure your account. See our ",
                        rx.link(
                            "Privacy Statement",
                            href="/privacy",
                            target="_blank",
                            color=styles.accent_text_color,
                            text_decoration="underline",
                        ),
                        ".",
                        size="1",
                        text_align="center",
                        line_height="1.5",
                    ),
                    spacing="4",
                    width="100%",
                ),
                max_width="28rem",
                padding="2rem",
                width="100%",
            ),
            min_height="100vh",
            padding="1rem",
        ),
        appearance="light",
        has_background=True,
    )


@rx.page(route=SIGN_IN_ROUTE, title="Sign In", on_load=AuthPageState.load)
def signin() -> rx.Component:
    form = rx.el.form(
        rx.vstack(
            _auth_input("Email", "email", type_="email", autocomplete="email"),
            _auth_input(
                "Password",
                "password",
                type_="password",
                autocomplete="current-password",
            ),
            rx.el.input(type="hidden", name="next", value=AuthPageState.next_path),
            rx.button("Sign in", type="submit", width="100%"),
            rx.hstack(
                rx.link("Create account", href=REGISTER_ROUTE),
                rx.link("Set up or reset password", href=FORGOT_PASSWORD_ROUTE),
                justify="between",
                align="center",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        action=auth_api_endpoint("login"),
        method="post",
        width="100%",
    )
    return _auth_shell(
        "Sign in to Debriefly",
        "Use your local account. Migrated Clerk users should set up a password first.",
        form,
    )


@rx.page(route=REGISTER_ROUTE, title="Create Account", on_load=AuthPageState.load)
def register() -> rx.Component:
    form = rx.el.form(
        rx.vstack(
            _auth_input("Email", "email", type_="email", autocomplete="email"),
            rx.button("Send verification link", type="submit", width="100%"),
            rx.link("Back to sign in", href=SIGN_IN_ROUTE),
            spacing="4",
            width="100%",
        ),
        action=auth_api_endpoint("register"),
        method="post",
        width="100%",
    )
    return _auth_shell(
        "Create an account",
        "We will email a one-time link. Open it to verify your address and choose your password.",
        form,
    )


@rx.page(
    route=FORGOT_PASSWORD_ROUTE,
    title="Set Up Password",
    on_load=AuthPageState.load,
)
def forgot_password() -> rx.Component:
    form = rx.el.form(
        rx.vstack(
            _auth_input("Email", "email", type_="email", autocomplete="email"),
            rx.button("Send one-time link", type="submit", width="100%"),
            rx.link("Back to sign in", href=SIGN_IN_ROUTE),
            spacing="4",
            width="100%",
        ),
        action=auth_api_endpoint("forgot-password"),
        method="post",
        width="100%",
    )
    return _auth_shell(
        "Set up or reset password",
        "This also activates a local password for an account migrated from Clerk.",
        form,
    )


@rx.page(
    route=RESET_PASSWORD_ROUTE,
    title="Choose Password",
    on_load=AuthPageState.load,
    meta=_TOKEN_PAGE_META,
)
def reset_password_page() -> rx.Component:
    form = rx.el.form(
        rx.vstack(
            rx.el.input(
                type="hidden",
                name="token",
                value=AuthPageState.reset_token,
            ),
            _auth_input(
                "New password (12+ characters)",
                "password",
                type_="password",
                autocomplete="new-password",
            ),
            _auth_input(
                "Confirm new password",
                "password_confirm",
                type_="password",
                autocomplete="new-password",
            ),
            rx.button("Save password", type="submit", width="100%"),
            rx.link("Back to sign in", href=SIGN_IN_ROUTE),
            spacing="4",
            width="100%",
        ),
        action=auth_api_endpoint("reset-password"),
        method="post",
        width="100%",
    )
    return _auth_shell(
        "Choose a password",
        "Saving a new password revokes every older Debriefly session.",
        rx.cond(
            AuthPageState.reset_token != "",
            form,
            rx.vstack(
                rx.callout(
                    "Open the complete one-time link from your email.",
                    icon="triangle-alert",
                    color_scheme="red",
                ),
                rx.link("Request another link", href=FORGOT_PASSWORD_ROUTE),
            ),
        ),
    )


@rx.page(
    route=VERIFY_EMAIL_ROUTE,
    title="Verify Email",
    on_load=AuthPageState.load,
    meta=_TOKEN_PAGE_META,
)
def verify_email_page() -> rx.Component:
    form = rx.el.form(
        rx.vstack(
            rx.el.input(
                type="hidden",
                name="token",
                value=AuthPageState.reset_token,
            ),
            _auth_input(
                "Password (12+ characters)",
                "password",
                type_="password",
                autocomplete="new-password",
            ),
            _auth_input(
                "Confirm password",
                "password_confirm",
                type_="password",
                autocomplete="new-password",
            ),
            rx.button(
                "Verify email and create account",
                type="submit",
                width="100%",
            ),
            rx.link("Back to sign in", href=SIGN_IN_ROUTE),
            spacing="4",
            width="100%",
        ),
        action=auth_api_endpoint("verify"),
        method="post",
        width="100%",
    )
    return _auth_shell(
        "Verify your email and choose a password",
        "Your account becomes active only after you save a password here.",
        rx.cond(
            AuthPageState.reset_token != "",
            form,
            rx.callout(
                "Open the complete verification link from your email.",
                icon="triangle-alert",
                color_scheme="red",
            ),
        ),
    )
