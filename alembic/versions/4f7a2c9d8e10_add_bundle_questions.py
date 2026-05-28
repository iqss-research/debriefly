"""add bundled question support

Revision ID: 4f7a2c9d8e10
Revises: 1a8c16cf3045
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4f7a2c9d8e10"
down_revision: Union[str, None] = "1a8c16cf3045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bundleitem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ordering", sa.Float(), nullable=False),
        sa.Column("field_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["field_id"],
            ["field.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("bundleitem")
