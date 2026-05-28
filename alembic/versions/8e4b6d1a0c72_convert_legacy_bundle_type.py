"""convert legacy bundle field type

Revision ID: 8e4b6d1a0c72
Revises: 7d2e1c8f4a90
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8e4b6d1a0c72"
down_revision: Union[str, None] = "7d2e1c8f4a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE field SET type_ = 'scale' WHERE type_ = 'bundle'")


def downgrade() -> None:
    pass
