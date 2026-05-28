"""add page break back option

Revision ID: a1b2c3d4e5f6
Revises: 8e4b6d1a0c72
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8e4b6d1a0c72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "allow_back",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.drop_column("allow_back")
