import json

from debriefly.reflex.backend.models import Form, QualtricsEmbedSession, User
from debriefly.reflex.components.analyze.state import (
    qualtrics_debriefing_context_chunks,
)
from debriefly.reflex.form_designer.pages.response import transcript_messages
from sqlmodel import Session, SQLModel, create_engine, select


def test_form_delete_cascades_qualtrics_embed_sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="abc123", user_id=user.user_id)
        form.qualtrics_embed_sessions.append(
            QualtricsEmbedSession(
                question_text="How clear was this question?",
                response_text="Very clear",
            )
        )
        session.add(user)
        session.add(form)
        session.commit()

        saved_form = session.exec(select(Form).where(Form.code == "abc123")).one()
        session.delete(saved_form)
        session.commit()

        assert session.exec(select(QualtricsEmbedSession)).all() == []


def test_transcript_messages_returns_clean_message_dicts():
    raw_transcript = json.dumps(
        [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "I chose yes."},
            {"role": "", "content": "ignored"},
            {"role": "assistant", "content": ""},
            "ignored",
        ]
    )

    assert transcript_messages(raw_transcript) == [
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "I chose yes."},
    ]


def test_analysis_context_includes_qualtrics_embed_transcripts():
    embed_session = QualtricsEmbedSession(
        form_id=1,
        public_id="embed-123",
        external_response_id="R_abc",
        external_question_id="QID1",
        question_text="How clear was this question?",
        response_text="Very clear",
    )

    context = "\n\n---\n\n".join(
        qualtrics_debriefing_context_chunks(
            [embed_session],
            {
                "embed-123": [
                    {"role": "assistant", "content": "What did clear mean to you?"},
                    {"role": "user", "content": "It was easy to understand."},
                ]
            },
        )
    )

    assert "Qualtrics Interview embed-123" in context
    assert "Qualtrics Response ID: R_abc" in context
    assert "Qualtrics Question ID: QID1" in context
    assert "Question: How clear was this question?" in context
    assert "Answer: Very clear" in context
    assert "user: It was easy to understand." in context
