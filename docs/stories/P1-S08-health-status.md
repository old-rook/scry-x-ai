# P1-S08 — Add Application Health and Dependency Status

## Objective

Provide the typed `/api/v1/health` contract and aggregate non-secret dependency status.

## Scope

- Aggregate backend health status.
- Database status.
- Scryfall status.
- Active rules status.
- AI/provider status.
- Non-secret provider/model summary.
- Rules verification and refresh summaries.

## Affected Files

- `backend/app/api/health.py`
- Health service and status interfaces.
- Frontend health types.
- Health test files.

## Dependencies

- P1-S03.
- P1-S05.
- P1-S06.
- P1-S07.

## Acceptance Criteria

- Health response uses the typed `/api/v1/health` contract.
- Database, Scryfall, rules, and AI status are individually represented.
- Credentials and private configuration are not returned.
- Dependency failures do not expose raw exception payloads.
- Rules status distinguishes verified local and latest known official versions.

## Testing Requirements

- Healthy dependency test.
- Degraded dependency tests.
- Database unavailable test.
- Scryfall unavailable test.
- Provider unavailable test.
- Stale rules status test.
- Secret-redaction test.
- Frontend contract test.

## Rollback Considerations

- Health can revert to process-liveness status.
- Dependency checks remain lightweight and non-destructive.

## Approval-Sensitive Items

- Whether detailed provider/model status is exposed before the admin-dashboard phase.
- External monitoring or status service integration.
