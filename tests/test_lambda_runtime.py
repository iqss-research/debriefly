"""Exercise the Lambda HTTP adapter against the real pinned Reflex runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
import reflex as rx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlmodel import Session

import debriefly.reflex.auth_api as auth_api
from debriefly.reflex.auth_api import register_auth_routes
from debriefly.reflex.auth_middleware import LocalAuthMiddleware
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import Field
from debriefly.reflex.components.chat.state import ChatState, QA
from debriefly.reflex.local_auth import get_auth_settings
import debriefly.reflex.auth_middleware as auth_middleware
import debriefly.serverless.state as lambda_state
from debriefly.serverless.state import SqlStateStore, snapshots
from debriefly.serverless.preview import exported_file
from debriefly.serverless.transport import (
    MAX_EVENT_BYTES,
    advance_timer,
    register_lambda_routes,
)


ORIGIN = "http://localhost:3000"
SIGNING_KEY = "lambda-runtime-tests-only-0123456789abcdef"


class LambdaRoundtripState(rx.State):
    count: int = 0
    seen_cookie: str = ""
    seen_origin: str = ""

    async def advance(self):
        self.count += 1
        yield
        self.count += 1
        yield rx.call_script("window.lambdaRoundtrip = true")

    def capture_request_headers(self):
        self.seen_cookie = self.router.headers.cookie
        self.seen_origin = self.router.headers.origin


class LambdaRoundtripChildState(LambdaRoundtripState):
    child_count: int = 0

    def advance_child(self):
        # The inherited value lives on the parent state. This catches a
        # deserializer that restores child values but loses parent pointers.
        self.count += 10
        self.child_count += 1


@pytest.fixture
def lambda_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_SECRET_KEY", SIGNING_KEY)
    monkeypatch.setenv("AUTH_PUBLIC_URL", ORIGIN)
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", ORIGIN)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.delenv("DEBRIEFLY_ORIGIN_VERIFY_SECRET", raising=False)
    get_auth_settings.cache_clear()
    engine = create_engine(
        f"sqlite:///{tmp_path / 'lambda-state.db'}",
        connect_args={"check_same_thread": False},
    )
    yield engine
    engine.dispose()
    get_auth_settings.cache_clear()


def _app(engine, *, version="test", explicit_state=True):
    app = rx.App(state=rx.State) if explicit_state else rx.App()
    app.add_middleware(LocalAuthMiddleware(), index=0)
    register_auth_routes(app.api)
    store = SqlStateStore(
        engine,
        signing_key=SIGNING_KEY,
        version=version,
        ttl_seconds=86400,
    )
    store.prepare()
    register_lambda_routes(app, store)
    return app


def _event(state, handler, *, token, **router_data):
    return {
        "token": token,
        "name": f"{state.get_full_name()}.{handler}",
        "payload": {},
        "router_data": {
            "pathname": "/",
            "asPath": "/",
            "query": {},
            **router_data,
        },
    }


def _post(client, event, *, origin=ORIGIN, **headers):
    return client.post(
        "/_lambda/event",
        json=event,
        headers={"Origin": origin, **headers},
    )


def _updates(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines() if line]


def _changed(updates, state, variable):
    return [
        update["delta"][state.get_full_name()][variable]
        for update in updates
        if variable in update.get("delta", {}).get(state.get_full_name(), {})
    ]


def test_generator_stream_preserves_reflex_updates_and_client_events(
    lambda_environment,
):
    token = str(uuid4())
    with TestClient(_app(lambda_environment).api) as client:
        updates = _updates(
            _post(client, _event(LambdaRoundtripState, "advance", token=token))
        )

    assert _changed(updates, LambdaRoundtripState, "count") == [1, 2]
    assert any(not update["final"] for update in updates)
    assert updates[-1]["final"] is True
    assert any(
        event["name"] == "_call_script"
        and event["payload"]["javascript_code"] == "window.lambdaRoundtrip = true"
        for update in updates
        for event in update.get("events", [])
    )


def test_uncompiled_app_enables_state_without_building_a_frontend(lambda_environment):
    app = _app(lambda_environment, explicit_state=False)
    with TestClient(app.api) as client:
        updates = _updates(
            _post(client, _event(LambdaRoundtripState, "advance", token=str(uuid4())))
        )
    assert _changed(updates, LambdaRoundtripState, "count") == [1, 2]


def test_backend_entrypoint_registers_pages_without_startup_database_writes(tmp_path):
    database = tmp_path / "must-not-be-created-at-import.db"
    environment = {
        **os.environ,
        "DB_URL": f"sqlite:///{database}",
        "AUTH_SECRET_KEY": SIGNING_KEY,
        "AUTH_PUBLIC_URL": ORIGIN,
        "AUTH_ALLOWED_ORIGINS": ORIGIN,
        "AUTH_COOKIE_SECURE": "false",
        "DEBRIEFLY_LOCAL_PREVIEW": "true",
        "DEBRIEFLY_RUNTIME_SECRET_ARN": "",
        "DEBRIEFLY_REQUIRE_DATABASE_URL": "false",
        "DEBRIEFLY_REQUIRE_POSTGRESQL": "false",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from debriefly.serverless.runtime import app; "
            "assert app.state is not None; "
            "assert app.get_load_events('/form/[form_code]'); "
            "assert app.get_load_events('/qualtrics/embed'); "
            "assert 'form_code' in app.state.computed_vars",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not database.exists()


def test_new_runtime_restores_parent_child_state_and_isolates_browser_tokens(
    lambda_environment,
):
    token = str(uuid4())
    with TestClient(_app(lambda_environment).api) as first:
        _updates(_post(first, _event(LambdaRoundtripState, "advance", token=token)))

    # A fresh App + state store shares no Python state with the first runtime.
    with TestClient(_app(lambda_environment).api) as second:
        child = _updates(
            _post(
                second,
                _event(LambdaRoundtripChildState, "advance_child", token=token),
            )
        )
        isolated = _updates(
            _post(
                second,
                _event(LambdaRoundtripState, "advance", token=str(uuid4())),
            )
        )

    assert _changed(child, LambdaRoundtripState, "count") == [12]
    assert _changed(child, LambdaRoundtripChildState, "child_count") == [1]
    assert _changed(isolated, LambdaRoundtripState, "count") == [1, 2]

    with TestClient(_app(lambda_environment).api) as third:
        restored = _updates(
            _post(third, _event(LambdaRoundtripState, "advance", token=token))
        )
    assert _changed(restored, LambdaRoundtripState, "count") == [13, 14]


def test_request_headers_override_spoofed_router_headers(lambda_environment):
    event = _event(
        LambdaRoundtripState,
        "capture_request_headers",
        token=str(uuid4()),
        headers={"cookie": "spoofed=admin", "origin": "https://attacker.example"},
    )
    with TestClient(_app(lambda_environment).api) as client:
        updates = _updates(_post(client, event, Cookie="browser=actual"))

    assert _changed(updates, LambdaRoundtripState, "seen_cookie") == ["browser=actual"]
    assert _changed(updates, LambdaRoundtripState, "seen_origin") == [ORIGIN]


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", ""])
def test_disallowed_or_missing_origin_cannot_dispatch_events(
    lambda_environment, origin
):
    with TestClient(_app(lambda_environment).api) as client:
        response = _post(
            client,
            _event(LambdaRoundtripState, "advance", token=str(uuid4())),
            origin=origin,
        )
    assert response.status_code == 403


def test_native_auth_posts_remain_reachable(lambda_environment):
    with TestClient(_app(lambda_environment).api) as client:
        response = client.post(
            "/_event/auth/login",
            data={"email": "test@example.org", "password": "unused"},
            headers={"Origin": "https://attacker.example"},
            follow_redirects=False,
        )
    assert response.status_code == 403
    assert response.text == "Forbidden"


def test_gateway_secret_protects_events_and_native_auth_with_public_liveness(
    lambda_environment, monkeypatch
):
    gateway_secret = "gateway-tests-only-0123456789abcdef0123456789abcdef"
    monkeypatch.setenv("DEBRIEFLY_ORIGIN_VERIFY_SECRET", gateway_secret)
    monkeypatch.setattr(auth_api.rx, "session", lambda: Session(lambda_environment))
    monkeypatch.setattr(auth_api, "authenticate_password", lambda *args: None)
    event = _event(LambdaRoundtripState, "advance", token=str(uuid4()))

    with TestClient(_app(lambda_environment).api) as client:
        health = client.get("/_lambda/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        for supplied_secret in (None, "incorrect-secret"):
            headers = {"Origin": ORIGIN}
            if supplied_secret is not None:
                headers["X-Debriefly-Origin-Verify"] = supplied_secret
            assert (
                client.post("/_lambda/event", json=event, headers=headers).status_code
                == 403
            )
            assert (
                client.post(
                    "/_event/auth/login",
                    data={"email": "gateway@example.test", "password": "unused"},
                    headers=headers,
                    follow_redirects=False,
                ).status_code
                == 403
            )

        headers = {"Origin": ORIGIN, "X-Debriefly-Origin-Verify": gateway_secret}
        updates = _updates(client.post("/_lambda/event", json=event, headers=headers))
        assert _changed(updates, LambdaRoundtripState, "count") == [1, 2]
        login = client.post(
            "/_event/auth/login",
            data={"email": "gateway@example.test", "password": "unused"},
            headers=headers,
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"].endswith("/signin?error=invalid")


def test_oversized_event_is_rejected_before_dispatch(lambda_environment):
    with TestClient(_app(lambda_environment).api) as client:
        response = client.post(
            "/_lambda/event",
            content=b"x" * (MAX_EVENT_BYTES + 1),
            headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        )
    assert response.status_code == 413
    assert response.json()["detail"] == "Event is too large"


def test_protected_handler_rechecks_cookie_instead_of_trusting_saved_state(
    lambda_environment, monkeypatch
):
    seen = []

    def expired_session(cookie_header, *, origin):
        seen.append((cookie_header, origin))
        return None

    monkeypatch.setattr(auth_middleware, "resolve_cookie_session", expired_session)
    with TestClient(_app(lambda_environment).api) as client:
        updates = _updates(
            _post(
                client,
                _event(
                    MainState,
                    "init",
                    token=str(uuid4()),
                    headers={"cookie": "spoofed=logged-in", "origin": ORIGIN},
                ),
                Cookie="browser=expired",
            )
        )

    assert seen == [("browser=expired", ORIGIN)]
    assert any(
        event["name"] == "_redirect" and event["payload"]["path"] == "/signin"
        for update in updates
        for event in update.get("events", [])
    )


def test_tampered_snapshot_fails_before_deserialization(
    lambda_environment, monkeypatch
):
    token = str(uuid4())
    with TestClient(_app(lambda_environment).api) as client:
        _updates(_post(client, _event(LambdaRoundtripState, "advance", token=token)))
    with lambda_environment.begin() as connection:
        connection.execute(update(snapshots).values(payload=b"tampered snapshot"))

    def forbidden_deserialization(payload):
        pytest.fail("A snapshot with an invalid HMAC must never be deserialized")

    monkeypatch.setattr(lambda_state, "deserialize_tree", forbidden_deserialization)
    with TestClient(_app(lambda_environment).api) as client:
        updates = _updates(
            _post(client, _event(LambdaRoundtripState, "advance", token=token))
        )

    assert len(updates) == 1
    assert updates[0].get("error")
    assert "tampered" not in updates[0]["error"]


def test_expired_or_versioned_snapshot_starts_a_fresh_browser_session(
    lambda_environment,
):
    token = str(uuid4())
    with TestClient(_app(lambda_environment).api) as first:
        _updates(_post(first, _event(LambdaRoundtripState, "advance", token=token)))
    with lambda_environment.begin() as connection:
        connection.execute(update(snapshots).values(expires_at=0))
    with TestClient(_app(lambda_environment).api) as expired:
        updates = _updates(
            _post(expired, _event(LambdaRoundtripState, "advance", token=token))
        )
    assert _changed(updates, LambdaRoundtripState, "count") == [1, 2]

    with TestClient(_app(lambda_environment, version="next-release").api) as versioned:
        updates = _updates(
            _post(versioned, _event(LambdaRoundtripState, "advance", token=token))
        )
    assert _changed(updates, LambdaRoundtripState, "count") == [1, 2]


def test_short_timer_events_preserve_minimum_maximum_and_idle_pause():
    chat = SimpleNamespace(
        _lambda_timer_updated_at=100.0,
        last_activity_time=100.0,
        elapsed_time=0,
        paused=False,
        show_finish=False,
        show_force_finish=False,
        field=SimpleNamespace(min_debriefing_time=10, max_debriefing_time=30),
    )

    advance_timer(chat, 110.0)
    assert chat.elapsed_time == 10
    assert chat.show_finish is True
    assert chat.show_force_finish is False

    advance_timer(chat, 140.0)
    assert chat.elapsed_time == 30
    assert chat.show_finish is False
    assert chat.show_force_finish is True

    chat.field.max_debriefing_time = 300
    chat._lambda_timer_updated_at = 200.0
    chat.elapsed_time = 0
    advance_timer(chat, 230.0)
    # Count active ticks at 205, 210 and 215; at 220 the 120-second
    # inactivity threshold pauses the clock, even if a request arrives late.
    assert chat.elapsed_time == 15
    assert chat.paused is True

    chat.last_activity_time = 230.0
    advance_timer(chat, 235.0)
    assert chat.elapsed_time == 20
    assert chat.paused is False


def test_timer_event_commits_state_and_schedules_a_short_followup(
    lambda_environment, monkeypatch
):
    token = str(uuid4())
    store = SqlStateStore(lambda_environment, SIGNING_KEY, version="test")
    store.prepare()
    with store.modify(token, rx.State) as state:
        chat = state.get_substate(ChatState.get_full_name().split("."))
        chat.loaded = True
        chat.done = False
        chat.field = Field(min_debriefing_time=10, max_debriefing_time=30)
        chat.last_activity_time = 100.0
        chat._lambda_timer_updated_at = 100.0

    monkeypatch.setattr("debriefly.serverless.transport.time.time", lambda: 110.0)
    app = _app(lambda_environment)
    with TestClient(app.api) as client:
        updates = _updates(_post(client, _event(ChatState, "count_time", token=token)))

    state_updates = [update for update in updates if "delta" in update]
    assert _changed(state_updates, ChatState, "elapsed_time") == [10]
    control = next(
        update["lambda_timer"] for update in updates if "lambda_timer" in update
    )
    assert control["active"] is True
    assert control["delay_ms"] == 5000
    assert control["event"]["name"] == f"{ChatState.get_full_name()}.count_time"
    assert app.background_tasks == set()

    # The followup instruction is emitted after the persisted state update.
    with store.modify(token, rx.State) as state:
        chat = state.get_substate(ChatState.get_full_name().split("."))
        assert chat.elapsed_time == 10
        assert chat.timer_running is True
        assert chat.show_finish is True


def test_paused_timer_stops_followups_and_answer_submission_resumes_them(
    lambda_environment, monkeypatch
):
    token = str(uuid4())
    store = SqlStateStore(lambda_environment, SIGNING_KEY, version="test")
    store.prepare()
    with store.modify(token, rx.State) as state:
        chat = state.get_substate(ChatState.get_full_name().split("."))
        chat.loaded = True
        chat.timer_running = True
        chat.field = Field(min_debriefing_time=10, max_debriefing_time=300)
        chat.last_activity_time = 100.0
        chat._lambda_timer_updated_at = 100.0

    async def fake_openai_reply(self, question):
        self.chat.append(QA(question=question, answer="Local test response"))
        yield

    monkeypatch.setitem(
        ChatState.event_handlers,
        "openai_process_question",
        ChatState.openai_process_question.copy(update={"fn": fake_openai_reply}),
    )
    clock = {"now": 230.0}
    monkeypatch.setattr(
        "debriefly.serverless.transport.time.time", lambda: clock["now"]
    )

    with TestClient(_app(lambda_environment).api) as client:
        paused = _updates(_post(client, _event(ChatState, "count_time", token=token)))
        assert _changed(paused, ChatState, "paused") == [True]
        control = next(
            update["lambda_timer"] for update in paused if "lambda_timer" in update
        )
        assert control["active"] is False

        clock["now"] = 235.0
        answer = _event(ChatState, "process_question", token=token)
        answer["payload"] = {"form_data": {"question": "I am back"}}
        resumed = _updates(_post(client, answer))
        assert _changed(resumed, ChatState, "paused") == [False]
        control = next(
            update["lambda_timer"] for update in resumed if "lambda_timer" in update
        )
        assert control["active"] is True

        clock["now"] = 240.0
        tick = _updates(_post(client, _event(ChatState, "count_time", token=token)))
        assert _changed(tick, ChatState, "elapsed_time") == [120]

    with store.modify(token, rx.State) as state:
        chat = state.get_substate(ChatState.get_full_name().split("."))
        assert chat.last_activity_time == 235.0
        assert chat.chat[-1].question == "I am back"
        assert chat.chat[-1].answer == "Local test response"


@pytest.mark.parametrize(
    ("route", "relative_file"),
    [
        ("/", "index.html"),
        ("/form/abc/", "form/[form_code]/index.html"),
        ("/form/chat", "form/chat/index.html"),
        ("/edit/form/9", "edit/form/[form_id]/index.html"),
        ("/edit/form/9/field", "edit/form/[form_id]/field/index.html"),
        ("/edit/form/9/field/2", "edit/form/[form_id]/field/[field_id]/index.html"),
        ("/responses/9", "responses/[form_id]/index.html"),
        ("/responses/9/analyze", "responses/[form_id]/analyze/index.html"),
    ],
)
def test_preview_resolves_homepage_literal_and_dynamic_exports(
    tmp_path, route, relative_file
):
    target = tmp_path / relative_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("Original exported UI")
    if route == "/form/chat":
        dynamic = tmp_path / "form/[form_code]/index.html"
        dynamic.parent.mkdir(parents=True, exist_ok=True)
        dynamic.write_text("Dynamic survey page")
    assert exported_file(tmp_path, route) == target


def test_preview_does_not_resolve_missing_files_or_paths_outside_export(tmp_path):
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (tmp_path / "outside.txt").write_text("Must never be served")
    assert exported_file(frontend, "/missing-page") is None
    assert exported_file(frontend, "../outside.txt") is None
