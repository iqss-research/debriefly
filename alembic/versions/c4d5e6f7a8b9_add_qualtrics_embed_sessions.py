"""add Qualtrics embed sessions

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-06-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qualtrics_embed_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("form_id", sa.Integer(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "external_response_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "external_question_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["form_id"],
            ["form.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_qualtrics_embed_session_form_id"),
        "qualtrics_embed_session",
        ["form_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_qualtrics_embed_session_public_id"),
        "qualtrics_embed_session",
        ["public_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_qualtrics_embed_session_public_id"),
        table_name="qualtrics_embed_session",
    )
    op.drop_index(
        op.f("ix_qualtrics_embed_session_form_id"),
        table_name="qualtrics_embed_session",
    )
    op.drop_table("qualtrics_embed_session")
