"""Add cost tiers and atomic paid-budget reservations.

Revision ID: 0004_atomic_paid_budget
Revises: 0003_provider_audit
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_atomic_paid_budget"
down_revision: str | None = "0003_provider_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_audit") as batch_op:
        batch_op.add_column(
            sa.Column("cost_tier", sa.String(length=10), nullable=False, server_default="free")
        )
        batch_op.create_check_constraint(
            "ck_provider_audit_cost_tier",
            "cost_tier IN ('free', 'paid')",
        )

    op.create_table(
        "ai_paid_monthly_budgets",
        sa.Column("month_start", sa.Date(), nullable=False, primary_key=True),
        sa.Column("cap_usd", sa.Numeric(20, 12), nullable=False),
        sa.Column("spent_usd", sa.Numeric(20, 12), nullable=False, server_default="0"),
        sa.Column("reserved_usd", sa.Numeric(20, 12), nullable=False, server_default="0"),
        sa.Column("unknown_cost", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("cap_usd > 0 AND cap_usd <= 5", name="ck_ai_paid_budget_cap"),
        sa.CheckConstraint("spent_usd >= 0", name="ck_ai_paid_budget_spent"),
        sa.CheckConstraint("reserved_usd >= 0", name="ck_ai_paid_budget_reserved"),
    )
    op.create_table(
        "ai_paid_budget_reservations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column(
            "month_start",
            sa.Date(),
            sa.ForeignKey("ai_paid_monthly_budgets.month_start"),
            nullable=False,
        ),
        sa.Column("amount_usd", sa.Numeric(20, 12), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("actual_cost_usd", sa.Numeric(20, 12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_usd > 0", name="ck_ai_paid_reservation_amount"),
        sa.CheckConstraint(
            "status IN ('reserved', 'settled', 'unknown')",
            name="ck_ai_paid_reservation_status",
        ),
        sa.CheckConstraint(
            "actual_cost_usd IS NULL OR actual_cost_usd >= 0",
            name="ck_ai_paid_reservation_actual_cost",
        ),
    )
    op.create_index(
        "ix_ai_paid_reservations_month_status",
        "ai_paid_budget_reservations",
        ["month_start", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_paid_reservations_month_status",
        table_name="ai_paid_budget_reservations",
    )
    op.drop_table("ai_paid_budget_reservations")
    op.drop_table("ai_paid_monthly_budgets")
    with op.batch_alter_table("provider_audit") as batch_op:
        batch_op.drop_constraint("ck_provider_audit_cost_tier", type_="check")
        batch_op.drop_column("cost_tier")
