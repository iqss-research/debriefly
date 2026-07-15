import asyncio
import logging
from datetime import datetime, timezone

import reflex as rx
from sqlmodel import select

from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import (
    Field,
    FieldValue,
    Form,
    HumanChatMessage,
    Response,
)
from debriefly.reflex.local_auth import resolve_cookie_session

logger = logging.getLogger(__name__)


def _get_owned_interview_field_value(session, field_value_id, user_id: str):
    try:
        parsed_field_value_id = int(field_value_id)
    except (TypeError, ValueError):
        return None
    if not user_id:
        return None

    return session.exec(
        select(FieldValue)
        .join(Field, FieldValue.field_id == Field.id)
        .join(Form, Field.form_id == Form.id)
        .join(Response, FieldValue.response_id == Response.id)
        .where(
            FieldValue.id == parsed_field_value_id,
            Form.user_id == user_id,
            Response.form_id == Form.id,
        )
    ).first()


class InterviewMessage(rx.Base):
    id: int
    role: str
    content: str
    end_chat: bool = False


class HumanInterviewSession(rx.Base):
    field_value_id: int
    client_token: str
    field_prompt: str
    form_name: str
    status: str  # "waiting", "active", "done"
    started_at: str


# ---------------------------------------------------------------------------
# Session detail state (researcher view of one interview)
# ---------------------------------------------------------------------------


class InterviewerState(MainState):
    messages: list[InterviewMessage] = []
    context_text: str = ""
    field_prompt: str = ""
    respondent_answer: str = ""
    session_done: bool = False
    loaded: bool = False
    error: str = ""
    _field_value_id: int = -1
    _last_msg_id: int = 0

    async def on_load(self):
        self.messages = []
        self.context_text = ""
        self.session_done = False
        self.loaded = False
        self.error = ""
        self._last_msg_id = 0

        raw_id = self.interview_session_id  # URL param set by Reflex routing
        try:
            fv_id = int(raw_id)
        except (ValueError, TypeError):
            self.error = "Invalid session ID."
            self.loaded = True
            return

        self._field_value_id = fv_id

        with rx.session() as session:
            field_value = _get_owned_interview_field_value(
                session, field_value_id=fv_id, user_id=self.user_id
            )
            if field_value is None:
                self.error = "Session not found."
                self.loaded = True
                return

            self.respondent_answer = field_value.value

            field = session.exec(
                select(Field).where(Field.id == field_value.field_id)
            ).first()
            if field:
                self.field_prompt = field.prompt

            # Load existing messages
            msgs = session.exec(
                select(HumanChatMessage)
                .where(HumanChatMessage.field_value_id == fv_id)
                .order_by(HumanChatMessage.id.asc())
            ).all()

            for m in msgs:
                if m.role == "context":
                    self.context_text = m.content
                else:
                    self.messages.append(
                        InterviewMessage(
                            id=m.id,
                            role=m.role,
                            content=m.content,
                            end_chat=m.end_chat,
                        )
                    )
                    if m.id > self._last_msg_id:
                        self._last_msg_id = m.id
                    if m.end_chat and m.role == "interviewer":
                        self.session_done = True

        self.loaded = True

        if not self.session_done:
            return InterviewerState.poll_for_new_messages()

    @rx.background
    async def poll_for_new_messages(self):
        """Polls DB every 2s for new respondent messages."""
        while True:
            await asyncio.sleep(2)
            async with self:
                if self.session_done:
                    return
                fv_id = self._field_value_id
                last_id = self._last_msg_id
                user_id = self.user_id
                cookie_header = getattr(self.router.headers, "cookie", "")
                origin = getattr(self.router.headers, "origin", "")

            active_user = resolve_cookie_session(cookie_header, origin=origin)
            if active_user is None or active_user.user_id != user_id:
                async with self:
                    self.error = "Your session has ended."
                    self.session_done = True
                return

            with rx.session() as session:
                if (
                    _get_owned_interview_field_value(
                        session, field_value_id=fv_id, user_id=user_id
                    )
                    is None
                ):
                    async with self:
                        self.error = "Session not found."
                        self.session_done = True
                    return
                new_msgs = session.exec(
                    select(HumanChatMessage)
                    .where(HumanChatMessage.field_value_id == fv_id)
                    .where(HumanChatMessage.id > last_id)
                    .where(HumanChatMessage.role == "user")
                    .order_by(HumanChatMessage.id.asc())
                ).all()

            if new_msgs:
                async with self:
                    for m in new_msgs:
                        self.messages.append(
                            InterviewMessage(
                                id=m.id,
                                role=m.role,
                                content=m.content,
                                end_chat=m.end_chat,
                            )
                        )
                        if m.id > self._last_msg_id:
                            self._last_msg_id = m.id

    async def send_reply(self, form_data: dict):
        content = (form_data.get("reply") or "").strip()
        if not content or self.session_done:
            return

        fv_id = self._field_value_id
        with rx.session() as session:
            if (
                _get_owned_interview_field_value(
                    session, field_value_id=fv_id, user_id=self.user_id
                )
                is None
            ):
                self.error = "Session not found."
                return
            msg = HumanChatMessage(
                field_value_id=fv_id,
                role="interviewer",
                content=content,
                end_chat=False,
            )
            session.add(msg)
            session.commit()
            session.refresh(msg)
            new_id = msg.id

        self.messages.append(
            InterviewMessage(id=new_id, role="interviewer", content=content)
        )
        if new_id > self._last_msg_id:
            self._last_msg_id = new_id

    async def end_interview(self):
        if self.session_done:
            return

        fv_id = self._field_value_id
        content = "The interview has been ended by the researcher."
        with rx.session() as session:
            if (
                _get_owned_interview_field_value(
                    session, field_value_id=fv_id, user_id=self.user_id
                )
                is None
            ):
                self.error = "Session not found."
                return
            msg = HumanChatMessage(
                field_value_id=fv_id,
                role="interviewer",
                content=content,
                end_chat=True,
            )
            session.add(msg)
            session.commit()
            session.refresh(msg)
            new_id = msg.id

        self.messages.append(
            InterviewMessage(
                id=new_id, role="interviewer", content=content, end_chat=True
            )
        )
        if new_id > self._last_msg_id:
            self._last_msg_id = new_id
        self.session_done = True


# ---------------------------------------------------------------------------
# Session list state (researcher dashboard)
# ---------------------------------------------------------------------------


class InterviewerListState(MainState):
    sessions: list[HumanInterviewSession] = []
    loaded: bool = False

    async def on_load(self):
        self.loaded = False
        self.sessions = []

        if not self.user_id:
            self.loaded = True
            return

        with rx.session() as session:
            # Find all FieldValues whose Field is in interviewer_mode
            # and whose Form belongs to the current user.
            results = session.exec(
                select(FieldValue, Field, Form, Response)
                .join(Field, FieldValue.field_id == Field.id)
                .join(Form, Field.form_id == Form.id)
                .join(Response, FieldValue.response_id == Response.id)
                .where(Field.interviewer_mode == True)  # noqa: E712
                .where(Form.user_id == self.user_id)
                .where(Response.form_id == Form.id)
            ).all()

            for fv, field, form, response in results:
                # Determine status from HumanChatMessage records
                msgs = session.exec(
                    select(HumanChatMessage)
                    .where(HumanChatMessage.field_value_id == fv.id)
                    .order_by(HumanChatMessage.id.asc())
                ).all()

                has_context = any(m.role == "context" for m in msgs)
                has_user_msg = any(m.role == "user" for m in msgs)
                is_done = any(m.role == "interviewer" and m.end_chat for m in msgs)

                if not has_context:
                    continue  # session not started yet

                if is_done:
                    status = "done"
                elif has_user_msg:
                    status = "active"
                else:
                    status = "waiting"

                started_at = min(
                    (m.created_at for m in msgs if m.role == "context"),
                    default=datetime.now(timezone.utc),
                )

                self.sessions.append(
                    HumanInterviewSession(
                        field_value_id=fv.id,
                        client_token=response.client_token,
                        field_prompt=field.prompt[:80]
                        + ("…" if len(field.prompt) > 80 else ""),
                        form_name=form.name,
                        status=status,
                        started_at=started_at.strftime("%Y-%m-%d %H:%M UTC"),
                    )
                )

        self.loaded = True
