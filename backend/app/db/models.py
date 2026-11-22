from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", server_default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="save-update, merge",
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="save-update, merge",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ProviderAudit(Base):
    __tablename__ = "provider_audit"
    __table_args__ = (
        CheckConstraint("outcome IN ('success', 'failure')", name="ck_provider_audit_outcome"),
        CheckConstraint("cost_tier IN ('free', 'paid')", name="ck_provider_audit_cost_tier"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_provider_audit_input_tokens",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_provider_audit_output_tokens",
        ),
        CheckConstraint(
            "reported_cost_usd IS NULL OR reported_cost_usd >= 0",
            name="ck_provider_audit_reported_cost",
        ),
        Index("ix_provider_audit_created_at", "created_at"),
        Index("ix_provider_audit_provider_created_at", "provider", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_tier: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="free",
        server_default="free",
    )
    error_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 12), nullable=True)


class AIPaidMonthlyBudget(Base):
    __tablename__ = "ai_paid_monthly_budgets"
    __table_args__ = (
        CheckConstraint("cap_usd > 0 AND cap_usd <= 5", name="ck_ai_paid_budget_cap"),
        CheckConstraint("spent_usd >= 0", name="ck_ai_paid_budget_spent"),
        CheckConstraint("reserved_usd >= 0", name="ck_ai_paid_budget_reserved"),
    )

    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    cap_usd: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    spent_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 12),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    reserved_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 12),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    unknown_cost: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AIPaidBudgetReservation(Base):
    __tablename__ = "ai_paid_budget_reservations"
    __table_args__ = (
        CheckConstraint("amount_usd > 0", name="ck_ai_paid_reservation_amount"),
        CheckConstraint(
            "status IN ('reserved', 'settled', 'unknown')",
            name="ck_ai_paid_reservation_status",
        ),
        CheckConstraint(
            "actual_cost_usd IS NULL OR actual_cost_usd >= 0",
            name="ck_ai_paid_reservation_actual_cost",
        ),
        Index("ix_ai_paid_reservations_month_status", "month_start", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    month_start: Mapped[date] = mapped_column(
        Date,
        ForeignKey("ai_paid_monthly_budgets.month_start"),
        nullable=False,
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    actual_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=func.now(),
    )
