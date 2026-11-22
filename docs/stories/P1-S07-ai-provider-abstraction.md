# P1-S07 — Implement AI Provider Abstraction

## Objective

Provide a provider-neutral AI interface with environment-only configuration, bounded retries, and fallback support.

## Scope

- Common generation and health provider interface.
- OpenRouter adapter.
- Optional Gemini adapter behind the same interface.
- Primary and fallback model configuration.
- Timeout, retry, and exponential-backoff settings.
- Provider error classification.
- Usage and failure audit recording.
- Paid-usage gate and spending-limit configuration.
- Secret-safe provider health summaries.

## Affected Files

- `backend/app/providers/`
- `backend/app/services/`
- `backend/app/core/config.py`
- `backend/app/repositories/`
- Provider usage/failure migrations.
- `.env.example`
- `backend/tests/providers/`

## Dependencies

- P1-S01.
- P1-S02.
- P1-S03.

## Acceptance Criteria

- Provider SDK types do not leak into routes or application services.
- Primary and fallback identifiers come from configuration.
- Retries are bounded.
- Failover applies only to eligible timeout, rate-limit, and provider-availability errors.
- Authentication and configuration failures do not trigger unrelated-provider retries.
- Paid usage defaults to disabled.
- Provider usage records do not expose secrets.
- Health output excludes private provider configuration.

## Testing Requirements

- Error-classification tests.
- Retry and backoff tests.
- Fallback ordering test.
- Authentication-no-failover test.
- Paid-usage gate test.
- Spending-limit test.
- Malformed provider response test.
- Context-size failure test.
- Usage and failure audit tests.

## Rollback Considerations

- Provider implementations can be disabled independently.
- Fallback configuration can revert to primary-only operation.
- No paid request occurs as part of rollback or testing.
- Audit tables can remain dormant.

## Approval-Sensitive Items

- OpenRouter SDK or HTTP integration.
- Gemini implementation scope.
- Primary and fallback model selections.
- Paid usage enablement and spending limits.
- Provider usage telemetry depth.
- External provider account requirements.
