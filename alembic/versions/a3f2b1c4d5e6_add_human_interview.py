"""Add human interview mode

Revision ID: a3f2b1c4d5e6
Revises: dc22fdc7aa86
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3f2b1c4d5e6"
down_revision: Union[str, None] = "dc22fdc7aa86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "interviewer_mode", sa.Boolean(), nullable=False, server_default="0"
            )
        )

    op.create_table(
        "human_chat_message",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "field_value_id",
            sa.Integer(),
            sa.ForeignKey("fieldvalue.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("end_chat", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("human_chat_message")

    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.drop_column("interviewer_mode")
