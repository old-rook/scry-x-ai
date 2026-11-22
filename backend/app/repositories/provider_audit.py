from decimal import Decimal
from sqlalchemy.orm import Session

from app.db.models import ProviderAudit


class ProviderAuditRepository:
    @staticmethod
    def record(
        session: Session,
        *,
        provider: str,
        model: str,
        outcome: str,
        cost_tier: str = "free",
        error_classification: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reported_cost_usd: Decimal | None = None,
    ) -> ProviderAudit:
        audit = ProviderAudit(
            provider=provider,
            model=model,
            outcome=outcome,
            cost_tier=cost_tier,
            error_classification=error_classification,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reported_cost_usd=reported_cost_usd,
        )
        session.add(audit)
        return audit
