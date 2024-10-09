import os
import asyncio
import reflex as rx
import reflex_clerk as clerk


class State(rx.State):
    user_id: str = ""
    counter: int = 0

    def increment(self):
        self.counter += 1

    def decrement(self):
        self.counter -= 1

    async def on_load(self):
        self.reset()
        state = await self.get_state(clerk.ClerkState)
        state.reset()
        yield State.get_logged_in_user

    @rx.background
    async def get_logged_in_user(self):
        while True:
            async with self:
                state = await self.get_state(clerk.ClerkState)
                if state.user_id is not None:
                    self.user_id = state.user_id
                    state.fetch_user()
                    # Do a one-time server-side operation with user_id here ..
                    break
                await asyncio.sleep(0.1)


def AppContent() -> rx.Component:
    return rx.vstack(
        rx.text(f"Hello {State.user_id}"),
        rx.text(f"{State.counter}"),
        rx.button("increment", on_click=State.increment),
        rx.button("decrement", on_click=State.decrement),
    )


def index() -> rx.Component:
    return clerk.clerk_provider(
        rx.center(
            clerk.signed_in(
                rx.vstack(AppContent(), clerk.user_button(), clerk.sign_out_button())
            ),
            clerk.signed_out(clerk.sign_in()),
        ),
        publishable_key=os.getenv("CLERK_PUBLISHABLE_KEY"),
        secret_key=os.getenv("CLERK_SECRET_KEY"),
    )


app = rx.App()
app.add_page(index, route="/", on_load=[State.on_load])
