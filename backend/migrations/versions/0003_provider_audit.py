"""Persist safe AI provider usage and failure audit records.

Revision ID: 0003_provider_audit
Revises: 0002_auth_identity
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_provider_audit"
down_revision: str | None = "0002_auth_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_audit",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("error_classification", sa.String(length=40), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reported_cost_usd", sa.Numeric(20, 12), nullable=True),
        sa.CheckConstraint("outcome IN ('success', 'failure')", name="ck_provider_audit_outcome"),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_provider_audit_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_provider_audit_output_tokens",
        ),
        sa.CheckConstraint(
            "reported_cost_usd IS NULL OR reported_cost_usd >= 0",
            name="ck_provider_audit_reported_cost",
        ),
    )
    op.create_index("ix_provider_audit_created_at", "provider_audit", ["created_at"])
    op.create_index(
        "ix_provider_audit_provider_created_at",
        "provider_audit",
        ["provider", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_audit_provider_created_at", table_name="provider_audit")
    op.drop_index("ix_provider_audit_created_at", table_name="provider_audit")
    op.drop_table("provider_audit")
