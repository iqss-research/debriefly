"""Request-scoped Reflex events with streamed updates and durable state."""

import asyncio
import hmac
import json
import logging
import os
import re
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from reflex import constants
from reflex.event import Event
from reflex.state import RouterData, StateUpdate
from reflex.utils import format

from debriefly.reflex.local_auth import origin_is_allowed


logger = logging.getLogger(__name__)
_TOKEN = re.compile(r"^[a-zA-Z0-9-]{16,128}$")
MAX_EVENT_BYTES = 1024 * 1024


def advance_timer(chat, now):
    """Advance the five-second interview clock using server time only."""
    previous = getattr(chat, "_lambda_timer_updated_at", 0.0)
    if previous <= 0:
        chat._lambda_timer_updated_at = now
        return
    ticks = max(0, int((now - previous) // 5))
    if ticks:
        # Match the original sampling rule: a tick counts only while idle <120s.
        active_end = min(now, chat.last_activity_time + 120 - 0.001)
        active_ticks = max(0, min(ticks, int((active_end - previous) // 5)))
        chat.elapsed_time = min(
            chat.elapsed_time + active_ticks * 5,
            int(chat.field.max_debriefing_time or 2**31),
        )
        chat._lambda_timer_updated_at = previous + ticks * 5
    chat.paused = now - chat.last_activity_time >= 120
    if chat.elapsed_time >= (chat.field.min_debriefing_time or 0):
        chat.show_finish = True
    if (
        chat.field.max_debriefing_time > 0
        and chat.elapsed_time >= chat.field.max_debriefing_time
    ):
        chat.show_finish = False
        chat.show_force_finish = True


def register_lambda_routes(app, store):
    """Reuse all application middleware and handlers, without Socket.IO tasks.

    Keep the terminal update until the transaction commits, so another event
    cannot observe a browser update whose corresponding snapshot is unsaved.
    """
    from debriefly.reflex.components.chat.state import ChatState

    # Normal Reflex enables state while compiling the frontend. Lambda imports
    # the backend directly and must initialize it without doing a build.
    app._enable_state()
    timer_name = f"{ChatState.get_full_name()}.count_time"

    @app.api.middleware("http")
    async def verify_origin_gateway(request, call_next):
        secret = os.getenv("DEBRIEFLY_ORIGIN_VERIFY_SECRET", "")
        if secret and request.url.path != "/_lambda/health":
            supplied = request.headers.get("x-debriefly-origin-verify", "")
            if not hmac.compare_digest(supplied, secret):
                return JSONResponse({"detail": "Forbidden"}, status_code=403)
        return await call_next(request)

    @app.api.get("/_lambda/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @app.api.post("/_lambda/event", include_in_schema=False)
    async def handle_event(request: Request):
        if not origin_is_allowed(request.headers.get("origin")):
            raise HTTPException(403, "Forbidden")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_EVENT_BYTES:
                raise HTTPException(413, "Event is too large")
        try:
            event = Event.parse_raw(bytes(body))
        except (ValueError, TypeError):
            raise HTTPException(400, "Invalid event") from None
        if not _TOKEN.fullmatch(event.token):
            raise HTTPException(400, "Invalid client token")
        # Never accept auth headers, client IP, or session ID from router_data.
        headers = dict(request.headers)
        headers.pop("x-debriefly-origin-verify", None)
        headers.pop("authorization", None)
        router = dict(event.router_data)
        router.update(
            {
                constants.RouteVar.QUERY: format.format_query_params(event.router_data),
                constants.RouteVar.CLIENT_TOKEN: event.token,
                constants.RouteVar.SESSION_ID: event.token,
                constants.RouteVar.HEADERS: headers,
                constants.RouteVar.CLIENT_IP: request.client.host
                if request.client
                else "",
            }
        )
        event.router_data = router

        async def updates():
            terminal = StateUpdate(final=True)
            timer_control = None
            try:
                with store.modify(event.token, app.state) as state:
                    state.router_data = router
                    state.router = RouterData(router)
                    chat = await state.get_state(ChatState)
                    if chat.timer_running and not chat.done:
                        advance_timer(chat, time.time())
                    preprocessed = await app._preprocess(state, event)
                    if preprocessed is not None:
                        terminal = preprocessed
                    elif event.name == timer_name:
                        # Browser ticks replace the only infinite background job.
                        if chat.loaded and not chat.done and not chat.error:
                            chat.timer_running = True
                            advance_timer(chat, time.time())
                        terminal = StateUpdate(delta=state.get_delta(), final=True)
                        state._clean()
                    else:
                        _, handler = state._get_event_handler(event)
                        if handler.is_background:
                            raise ValueError("Unsupported background handler in Lambda")
                        async for update in state._process(event):
                            update = await app._postprocess(state, event, update)
                            if update.final:
                                terminal = update
                            else:
                                yield update.json() + "\n"
                                await asyncio.sleep(0)
                    active = bool(
                        chat.timer_running
                        and not chat.done
                        and not chat.error
                        and not chat.paused
                    )
                    if event.name == timer_name or chat.timer_running:
                        timer_control = {
                            "lambda_timer": {
                                "event": {
                                    "token": event.token,
                                    "name": timer_name,
                                    "router_data": {
                                        k: v
                                        for k, v in event.router_data.items()
                                        if k
                                        not in {
                                            constants.RouteVar.HEADERS,
                                            constants.RouteVar.CLIENT_IP,
                                        }
                                    },
                                    "payload": {},
                                },
                                "active": active,
                                "delay_ms": 5000,
                            }
                        }
                # The SQL transaction has committed before final is delivered.
                yield terminal.json() + "\n"
                if timer_control is not None:
                    yield json.dumps(timer_control) + "\n"
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Lambda event failed")
                yield json.dumps(
                    {
                        "error": "The request could not finish. Reload the page before trying again."
                    }
                ) + "\n"

        return StreamingResponse(
            updates(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
