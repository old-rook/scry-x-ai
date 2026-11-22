"""Add local auth identity and role fields to users.

Revision ID: 0002_auth_identity
Revises: 0001_initial_persistence
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_auth_identity"
down_revision: str | None = "0001_initial_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("role", sa.String(length=20), nullable=False, server_default="user")
        )
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        )
        batch_op.create_unique_constraint("uq_users_email", ["email"])
        batch_op.create_check_constraint("ck_users_role", "role IN ('user', 'admin')")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("role")
        batch_op.drop_column("password_hash")
        batch_op.drop_column("email")
