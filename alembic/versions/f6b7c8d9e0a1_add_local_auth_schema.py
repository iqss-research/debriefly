"""Add local authentication storage without changing ownership keys.

Revision ID: f6b7c8d9e0a1
Revises: a3f2b1c4d5e6
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6b7c8d9e0a1"
down_revision: Union[str, None] = "a3f2b1c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep user.user_id as the stable internal ownership key. These columns are
    # additive so the Clerk-backed application can run during the transition.
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("email_normalized", sa.String(length=320), nullable=True)
        )
        batch_op.add_column(
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.add_column(
            sa.Column(
                "role",
                sa.String(length=16),
                nullable=False,
                server_default="user",
            )
        )
        batch_op.add_column(
            sa.Column(
                "auth_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        # Nullable timestamps avoid a table-wide backfill during this additive
        # revision. New model instances populate both values in application code.
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
        )
        # Match User.__table_args__ exactly.  A named unique constraint is
        # portable across SQLite and PostgreSQL and prevents a follow-up
        # autogenerate revision that merely swaps a unique index for a unique
        # constraint.
        batch_op.create_unique_constraint(
            "uq_user_email_normalized",
            ["email_normalized"],
        )

    op.create_table(
        "user_identity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            server_default="clerk",
        ),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_normalized", sa.String(length=320), nullable=True),
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "link_source",
            sa.String(length=32),
            nullable=False,
            server_default="import",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "issuer",
            "subject",
            name="uq_user_identity_provider_issuer_subject",
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "issuer",
            name="uq_user_identity_user_provider_issuer",
        ),
    )
    op.create_index(
        "ix_user_identity_user_id",
        "user_identity",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "local_credential",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "auth_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_digest",
            name="uq_auth_session_token_digest",
        ),
    )
    op.create_index(
        "ix_auth_session_user_id",
        "auth_session",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_session_expires_at",
        "auth_session",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "auth_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_auth_token_token_digest"),
    )
    op.create_index(
        "ix_auth_token_user_id",
        "auth_token",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_token_expires_at",
        "auth_token",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("auth_token")
    op.drop_table("auth_session")
    op.drop_table("local_credential")
    op.drop_table("user_identity")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_constraint("uq_user_email_normalized", type_="unique")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("auth_version")
        batch_op.drop_column("role")
        batch_op.drop_column("status")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_normalized")
