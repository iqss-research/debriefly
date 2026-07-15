"""Every-event authorization for researcher state handlers."""

from __future__ import annotations

import reflex as rx
from reflex.event import Event, fix_events, get_hydrate_event
from reflex.middleware import Middleware
from reflex.state import BaseState, StateUpdate

from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.local_auth import resolve_cookie_session


class LocalAuthMiddleware(Middleware):
    """Reject protected Reflex events before their handlers are invoked.

    Page redirects are useful UX, but they are not an authorization boundary:
    Reflex event names can be called directly. Researcher states inherit from
    ``MainState``; anonymous survey respondent states deliberately do not.
    """

    async def preprocess(
        self,
        app,
        state: BaseState,
        event: Event,
    ) -> StateUpdate | None:
        is_hydrate = event.name == get_hydrate_event(state)

        if not is_hydrate:
            state_path = event.name.rpartition(".")[0]
            try:
                handler_class = type(state).get_class_substate(state_path)
            except (IndexError, ValueError):
                return None
            if not issubclass(handler_class, MainState):
                return None

        cookie_header = getattr(state.router.headers, "cookie", "")
        origin = getattr(state.router.headers, "origin", "")
        user = resolve_cookie_session(cookie_header, origin=origin)
        main_state = await state.get_state(MainState)
        if user is None:
            main_state.reset()
            main_state._clear_authentication()
            # Public pages must hydrate anonymously. Protected page on-load
            # events are redirected when they subsequently reach this middleware.
            if is_hydrate:
                return None
            return StateUpdate(
                events=fix_events(
                    [rx.redirect("/signin", replace=True)],
                    event.token,
                    event.router_data,
                )
            )

        if main_state.user_id and main_state.user_id != user.user_id:
            # Reflex keeps its client token in sessionStorage across navigation;
            # reset all researcher substates before a different user can reuse it.
            main_state.reset()
        main_state._set_authenticated_user(user)
        return None
