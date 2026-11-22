# P1-S02 — Establish Typed API and Configuration Contracts

## Objective

Create validated backend schemas and matching frontend API types for the Phase 1 foundation endpoints.

## Scope

- Pydantic schemas for health, card, answer, citation, and conversation contracts.
- Centralized validated environment configuration.
- Typed frontend API client and response models.
- OpenAPI or generated-contract documentation.
- Contract-mismatch tests.

## Affected Files

- `backend/app/schemas/`
- `backend/app/core/config.py`
- `backend/app/api/`
- `frontend/lib/`
- Contract test files.
- `.env.example`

## Dependencies

- P1-S01.

## Acceptance Criteria

- Malformed API requests are rejected by Pydantic validation.
- Card, answer, source, and conversation response types are explicit.
- Frontend types match backend contracts.
- Contract mismatch is detected by automated tests.
- Secret settings are absent from frontend types and API responses.

## Testing Requirements

- Schema validation tests.
- OpenAPI or generated-schema snapshot test.
- Frontend/backend contract integration test.
- Invalid and boundary input tests.

## Rollback Considerations

- Contract additions can remain dormant if dependent implementations are removed.
- No database or external-service state is affected.

## Approval-Sensitive Items

- Final answer-source and conversation schemas should be reviewed before persistence implementation.
- Generated contract versus manually maintained frontend types requires a separate implementation choice.
