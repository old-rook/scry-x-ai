# P1-S04 — Implement Authentication and Authorization Foundation

## Objective

Create server-side identity, role, and ownership primitives for registered users and administrators.

## Scope

- Identity and role representation.
- Session or JWT authentication adapter.
- Authenticated-route dependency.
- Administrator-route dependency.
- Conversation ownership helpers.
- Secret-safe authentication configuration.
- Authentication and authorization error handling.

## Affected Files

- `backend/app/core/`
- `backend/app/api/`
- `backend/app/services/`
- `backend/app/repositories/`
- Authentication test files.
- Frontend account/session integration points.

## Dependencies

- P1-S02.
- P1-S03.

## Acceptance Criteria

- Missing or invalid credentials are rejected by authenticated routes.
- A user cannot access another user's conversation.
- Non-admin users cannot access admin routes.
- Guest state is not uploaded or persisted automatically.
- Authentication logs contain no credentials or tokens.
- Admin responses expose no secrets or private configuration.

## Testing Requirements

- Missing, malformed, expired, and valid credential tests.
- Cross-user conversation access tests.
- Admin authorization tests.
- Ownership helper tests.
- Session or JWT security regression tests.

## Rollback Considerations

- Authentication can remain disabled from public routers until complete.
- Database changes must be independently reversible.
- Guest flows remain usable without an authenticated identity.

## Approval-Sensitive Items

- Server-side sessions versus JWTs.
- Local credentials versus external OAuth.
- Identity fields and provider identity mapping.
- Token lifetime and cookie settings.
- Authentication library and dependency selection.
- Password-reset and account lifecycle scope.
