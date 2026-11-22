from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.db.models import AIPaidBudgetReservation, AIPaidMonthlyBudget


@dataclass(frozen=True)
class BudgetReservation:
    id: UUID
    month_start: date
    amount_usd: Decimal


class PaidBudgetRepository:
    @staticmethod
    def reserve(
        session: Session,
        *,
        month_start: date,
        cap_usd: Decimal,
        minimum_remaining_usd: Decimal,
    ) -> BudgetReservation | None:
        reservation_id = uuid4()
        try:
            dialect = session.get_bind().dialect.name
            values = {
                "month_start": month_start,
                "cap_usd": cap_usd,
                "spent_usd": Decimal("0"),
                "reserved_usd": Decimal("0"),
                "unknown_cost": False,
            }
            if dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            elif dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                raise RuntimeError("Unsupported database for atomic paid budget reservations")
            insert_statement = insert(AIPaidMonthlyBudget).values(**values)
            session.execute(
                insert_statement.on_conflict_do_nothing(
                    index_elements=[AIPaidMonthlyBudget.month_start]
                )
            )

            effective_cap = case(
                (AIPaidMonthlyBudget.cap_usd <= cap_usd, AIPaidMonthlyBudget.cap_usd),
                else_=cap_usd,
            )
            remaining_budget = effective_cap - AIPaidMonthlyBudget.spent_usd
            update_result = session.execute(
                update(AIPaidMonthlyBudget)
                .where(
                    AIPaidMonthlyBudget.month_start == month_start,
                    AIPaidMonthlyBudget.unknown_cost.is_(False),
                    AIPaidMonthlyBudget.reserved_usd == 0,
                    AIPaidMonthlyBudget.spent_usd < effective_cap,
                    remaining_budget >= minimum_remaining_usd,
                )
                .values(
                    cap_usd=effective_cap,
                    reserved_usd=remaining_budget,
                    updated_at=func.now(),
                )
            )
            if update_result.rowcount != 1:
                session.commit()
                return None

            reservation_amount = session.scalar(
                select(AIPaidMonthlyBudget.reserved_usd).where(
                    AIPaidMonthlyBudget.month_start == month_start
                )
            )
            if reservation_amount is None:
                raise RuntimeError("Paid budget reservation amount is unavailable")
            session.add(
                AIPaidBudgetReservation(
                    id=reservation_id,
                    month_start=month_start,
                    amount_usd=reservation_amount,
                    status="reserved",
                )
            )
            session.commit()
            return BudgetReservation(reservation_id, month_start, reservation_amount)
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def settle(
        session: Session,
        reservation: BudgetReservation,
        *,
        actual_cost_usd: Decimal,
    ) -> None:
        try:
            update_result = session.execute(
                update(AIPaidMonthlyBudget)
                .where(
                    AIPaidMonthlyBudget.month_start == reservation.month_start,
                    AIPaidMonthlyBudget.reserved_usd >= reservation.amount_usd,
                )
                .values(
                    reserved_usd=AIPaidMonthlyBudget.reserved_usd - reservation.amount_usd,
                    spent_usd=AIPaidMonthlyBudget.spent_usd + actual_cost_usd,
                    updated_at=func.now(),
                )
            )
            reservation_result = session.execute(
                update(AIPaidBudgetReservation)
                .where(
                    AIPaidBudgetReservation.id == reservation.id,
                    AIPaidBudgetReservation.status == "reserved",
                )
                .values(
                    status="settled",
                    actual_cost_usd=actual_cost_usd,
                    updated_at=func.now(),
                )
            )
            if update_result.rowcount != 1 or reservation_result.rowcount != 1:
                raise RuntimeError("Paid budget reservation could not be settled")
            session.commit()
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def mark_unknown(session: Session, reservation: BudgetReservation) -> None:
        try:
            session.execute(
                update(AIPaidMonthlyBudget)
                .where(AIPaidMonthlyBudget.month_start == reservation.month_start)
                .values(unknown_cost=True, updated_at=func.now())
            )
            reservation_result = session.execute(
                update(AIPaidBudgetReservation)
                .where(
                    AIPaidBudgetReservation.id == reservation.id,
                    AIPaidBudgetReservation.status == "reserved",
                )
                .values(status="unknown", updated_at=func.now())
            )
            if reservation_result.rowcount != 1:
                raise RuntimeError("Paid budget reservation could not be marked unknown")
            session.commit()
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def monthly_budget(session: Session, month_start: date) -> AIPaidMonthlyBudget | None:
        return session.scalar(
            select(AIPaidMonthlyBudget).where(AIPaidMonthlyBudget.month_start == month_start)
        )
