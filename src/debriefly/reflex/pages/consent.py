import reflex as rx
from datetime import datetime, timezone
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import User

import logging

logger = logging.getLogger(__name__)

TOS_VERSION = "2025-06-19"


class ConsentState(MainState):
    """
    Re-uses MainState so we already have self.user loaded.
    """

    async def on_load(self):
        # If the user already accepted this version, skip the page.
        if self.user.tos_version == TOS_VERSION:
            logger.info("Accepted TOS version %s, skipping /consent", TOS_VERSION)
            return rx.redirect("/")

    async def confirm(self):
        if not await self.sync_user_from_session():
            return rx.redirect("/signin")
        accepted_at = datetime.now(timezone.utc)
        with rx.session() as s:
            user = s.get(User, self.user_id)
            if user is None:
                return rx.redirect("/signin")
            user.tos_version = self.TOS_VERSION
            user.tos_accepted_at = accepted_at
            user.updated_at = accepted_at
            s.add(user)
            s.commit()

        return rx.redirect("/")


@rx.page(
    route="/consent",
    title="Consent",
    on_load=[MainState.init, ConsentState.on_load],
)
def consent() -> rx.Component:
    content = rx.center(
        rx.card(
            rx.vstack(
                rx.markdown(
                    "By clicking **I CONFIRM** below I accept the "
                    'Debriefly <a href="/terms" target="_blank">Terms of Service</a> '
                    "and consent to the collection and use of my data as described "
                    'in the TK <a href="/privacy" target="_blank">Privacy Statement</a>.'
                ),
                rx.button(
                    "I CONFIRM",
                    color_scheme="green",
                    on_click=ConsentState.confirm,
                ),
                spacing="5",
            ),
            max_width="32rem",
            text_align="center",
            p="6",
        ),
        min_h="100vh",
    )

    return content
