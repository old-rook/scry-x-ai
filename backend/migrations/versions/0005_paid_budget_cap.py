"""Raise the paid budget cap to USD 20.

Revision ID: 0005_paid_budget_cap
Revises: 0004_atomic_paid_budget
"""
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision: str = "0005_paid_budget_cap"
down_revision: str | None = "0004_atomic_paid_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_paid_monthly_budgets") as batch_op:
        batch_op.drop_constraint("ck_ai_paid_budget_cap", type_="check")
        batch_op.create_check_constraint(
            "ck_ai_paid_budget_cap",
            "cap_usd > 0 AND cap_usd <= 20",
        )

    now = datetime.now(timezone.utc)
    current_month = sa.table(
        "ai_paid_monthly_budgets",
        sa.column("month_start", sa.Date()),
        sa.column("cap_usd", sa.Numeric(20, 12)),
    )
    op.execute(
        sa.update(current_month)
        .where(
            current_month.c.month_start == now.date().replace(day=1),
            current_month.c.cap_usd < Decimal("20"),
        )
        .values(cap_usd=Decimal("20"))
    )


def downgrade() -> None:
    budgets = sa.table(
        "ai_paid_monthly_budgets",
        sa.column("cap_usd", sa.Numeric(20, 12)),
    )
    op.execute(
        sa.update(budgets)
        .where(budgets.c.cap_usd > Decimal("5"))
        .values(cap_usd=Decimal("5"))
    )
    with op.batch_alter_table("ai_paid_monthly_budgets") as batch_op:
        batch_op.drop_constraint("ck_ai_paid_budget_cap", type_="check")
        batch_op.create_check_constraint(
            "ck_ai_paid_budget_cap",
            "cap_usd > 0 AND cap_usd <= 5",
        )
