"""normalize bundled field flags

Revision ID: 7d2e1c8f4a90
Revises: 6b1f2a4c9d30
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7d2e1c8f4a90"
down_revision: Union[str, None] = "6b1f2a4c9d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
        UPDATE field
        SET bundled = :bundled
        WHERE id NOT IN (
            SELECT DISTINCT field_id
            FROM bundleitem
        )
        """
        ),
        {"bundled": False},
    )
    bind.execute(
        sa.text(
            """
        UPDATE field
        SET bundled = :bundled
        WHERE id IN (
            SELECT DISTINCT field_id
            FROM bundleitem
        )
        """
        ),
        {"bundled": True},
    )


def downgrade() -> None:
    pass
