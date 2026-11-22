# P1-S03 — Configure PostgreSQL Access

## Objective

Add environment-driven PostgreSQL connectivity and repository boundaries without finalizing the complete domain schema.

## Scope

- Database engine/session configuration.
- Repository or data-access abstractions.
- Migration framework configuration.
- Initial approved MVP persistence migration.
- Database health reporting.
- Connection and transaction lifecycle.

## Affected Files

- `backend/app/repositories/`
- `backend/app/db/`
- Migration directory.
- Database test files.
- `.env.example`

## Dependencies

- P1-S01.
- P1-S02.

## Acceptance Criteria

- The database URL is environment-only.
- Route handlers do not execute SQL directly.
- Repository operations are unit and integration testable.
- A migration creates and rolls back a clean foundation database.
- Database health reports status without credentials.
- Database failures are explicit and observable.

## Testing Requirements

- Database connectivity test.
- Repository CRUD test.
- Migration upgrade and downgrade test.
- Session and connection-failure test.
- Database health test.

## Rollback Considerations

- Migration rollback restores the pre-story schema.
- No user data is deleted automatically.
- Provider and rules work remains independent of migration success.

## Approval-Sensitive Items

- PostgreSQL hosting provider.
- SQLAlchemy or alternative PostgreSQL library.
- Migration framework.
- Initial schema and field constraints.
- Initial MVP entities and migrations.

## Approved Implementation Decisions

- Use SQLAlchemy 2, Alembic, and Psycopg 3.
- Create the initial `users`, `conversations`, and `messages` tables.
- Keep the initial user record limited to a UUID and creation timestamp; identity and role fields belong to the authentication story.
- Use in-memory SQLite for unit and migration tests until a PostgreSQL test instance is available. PostgreSQL integration testing remains outstanding.
- Do not select or add a PostgreSQL hosting provider in this story.
