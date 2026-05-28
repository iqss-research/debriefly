"""drop stray field parent reference if present

Revision ID: 1a8c16cf3045
Revises: b7a0c5e4a2d1
Create Date: 2026-05-27 19:44:29.480703

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "1a8c16cf3045"
down_revision: Union[str, None] = "b7a0c5e4a2d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _field_has_column(column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns("field")}


def _field_has_foreign_key(foreign_key_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return foreign_key_name in {
        foreign_key["name"] for foreign_key in inspector.get_foreign_keys("field")
    }


def upgrade() -> None:
    if not _field_has_column("parent_id"):
        return

    with op.batch_alter_table("field", schema=None) as batch_op:
        if op.get_bind().dialect.name != "sqlite" and _field_has_foreign_key(
            "fk_field_parent_id_field"
        ):
            batch_op.drop_constraint("fk_field_parent_id_field", type_="foreignkey")
        batch_op.drop_column("parent_id")


def downgrade() -> None:
    # The repository's migration history never creates field.parent_id, so the
    # reverse migration should leave the historical schema unchanged.
    pass
