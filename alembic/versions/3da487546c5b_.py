"""empty message

Revision ID: 3da487546c5b
Revises: e9e34733643c
Create Date: 2025-06-16 10:02:14.629789

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3da487546c5b"
down_revision: Union[str, None] = "e9e34733643c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE fieldtype ADD VALUE IF NOT EXISTS 'scale';")


def downgrade() -> None:
    # We simply leave the unused enum value untouched. See:
    # https://supabase.com/docs/guides/database/postgres/enums#removing-enum-values
    pass
