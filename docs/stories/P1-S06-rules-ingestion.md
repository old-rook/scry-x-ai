# P1-S06 — Implement Comprehensive Rules Ingestion

## Objective

Create validated, locally stored, versioned Comprehensive Rules data with safe activation and rollback.

## Scope

- Official rules source configuration.
- Download to staging storage.
- Encoding and structure validation.
- Plausible rule-count and section checks.
- SHA-256 checksum calculation.
- Parsing and indexed storage.
- Atomic activation and previous-version preservation.
- Rules refresh status and failure recording.
- Startup and scheduled freshness orchestration.
- Authorized manual refresh entry point.

## Affected Files

- `backend/app/rules/`
- `backend/app/repositories/`
- `backend/app/services/rules_service.py`
- `backend/app/api/rules.py`
- Rules migration entities.
- Staged and active rules storage.
- `backend/tests/rules/`

## Dependencies

- P1-S01.
- P1-S02.
- P1-S03.

## Acceptance Criteria

- Failed validation never activates a ruleset.
- The previous active ruleset remains usable after failure.
- Version, publication date, verification date, checksum, and status are recorded.
- Latest verified local rules and latest known official rules are distinguishable.
- Stale startup state triggers verification when older than 24 hours.
- Scheduled verification runs at least every 24 hours.
- Manual refresh is authorized and observable.
- Refresh work does not block normal request handling.

## Testing Requirements

- Valid rules fixture ingestion.
- Malformed encoding and structure tests.
- Implausible rule-count test.
- Missing-section test.
- Checksum mismatch test.
- Successful activation test.
- Failed-update rollback test.
- Stale startup verification test.
- Concurrent refresh protection test.

## Rollback Considerations

- Every previously activated valid ruleset remains available.
- Staging failures leave or re-activate the prior ruleset.
- Staged files and incomplete records remain inactive and removable.
- Answer behavior is not coupled to this story.

## Approval-Sensitive Items

- Official rules source URL and retrieval method.
- Rules storage format.
- Parser and lexical indexing implementation.
- Scheduler and infrastructure.
- Rules database schema additions.
- Manual refresh endpoint exposure.
