"""Add model and prompt provenance to interviews.

Revision ID: 2f4c8a1d9e7b
Revises: f6b7c8d9e0a1
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "2f4c8a1d9e7b"
down_revision: Union[str, None] = "f6b7c8d9e0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_provenance_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "interview_model",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "interview_model_versions",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "interview_prompt_version",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "interview_system_prompt",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "interview_initial_prompt",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )


def _drop_provenance_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.drop_column("interview_initial_prompt")
        batch_op.drop_column("interview_system_prompt")
        batch_op.drop_column("interview_prompt_version")
        batch_op.drop_column("interview_model_versions")
        batch_op.drop_column("interview_model")


def upgrade() -> None:
    _add_provenance_columns("fieldvalue")
    _add_provenance_columns("qualtrics_embed_session")


def downgrade() -> None:
    _drop_provenance_columns("qualtrics_embed_session")
    _drop_provenance_columns("fieldvalue")
