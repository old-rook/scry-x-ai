# P1-S05 — Implement Scryfall Card Provider Adapter

## Objective

Provide normalized card search and ruling retrieval behind an isolated card-provider interface.

## Scope

- Scryfall HTTP adapter.
- Timeout and bounded retry behavior.
- Card search and card detail normalization.
- Card-ruling normalization.
- Optional cache-backed lookup.
- Explicit provider, rate-limit, and network errors.
- Card-provider health check.

## Affected Files

- `backend/app/providers/`
- `backend/app/services/card_service.py`
- `backend/app/api/cards.py`
- Cache or repository components, if approved.
- `backend/tests/providers/`
- `backend/tests/api/`

## Dependencies

- P1-S01.
- P1-S02.
- P1-S03, if cache persistence is included.

## Acceptance Criteria

- Scryfall-specific fields do not leak into core models or routes.
- Card names, Oracle text, metadata, images, and rulings use normalized fields.
- Search limits are bounded.
- Timeout, rate-limit, and malformed-provider responses produce explicit API errors.
- Cache entries include source and retrieval timestamps.
- Oracle text is never represented as AI-generated source text.

## Testing Requirements

- Scryfall response fixture tests.
- Card normalization tests.
- Timeout, HTTP error, malformed response, and rate-limit tests.
- Cache hit and miss tests when caching is enabled.
- Health and degraded-status tests.

## Rollback Considerations

- Scryfall remains replaceable behind the card-provider interface.
- Cache entries or storage can be removed without changing core contracts.
- Failure can return an explicit unavailable status instead of stale results.

## Approval-Sensitive Items

- Scryfall credentials, if required.
- Cache storage choice and retention duration.
- External cache infrastructure.
- Gatherer integration beyond Scryfall.
