"""add bundled field flag

Revision ID: 6b1f2a4c9d30
Revises: 4f7a2c9d8e10
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b1f2a4c9d30"
down_revision: Union[str, None] = "4f7a2c9d8e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "bundled", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.drop_column("bundled")
