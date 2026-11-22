# P1-S01 — Create Project Foundations

## Objective

Create minimal independently deployable Next.js and FastAPI project structures with development entry points and test configuration.

## Scope

- FastAPI application factory.
- Backend `/api/v1/health` route.
- Next.js App Router project shell.
- Tailwind CSS and shadcn/ui-compatible base setup.
- Backend and frontend test directories.
- Non-secret `.env.example`.
- Development scripts and ignore rules.
- Dark-mode-ready base styling.

## Affected Files

- `frontend/app/`
- `frontend/components/`
- `frontend/lib/`
- `frontend/tests/`
- `backend/app/api/`
- `backend/app/core/`
- `backend/tests/`
- Project configuration and environment-template files.

## Dependencies

- None.

## Acceptance Criteria

- The backend starts independently and exposes a health response.
- The frontend starts independently.
- The frontend contains no provider secrets or database credentials.
- Generated databases, staged files, secrets, logs, dependencies, and coverage artifacts are ignored.
- Backend startup tests and frontend build/smoke tests pass.

## Testing Requirements

- FastAPI startup test.
- Health response test.
- Frontend build or smoke test.
- Environment-template validation.

## Rollback Considerations

- Remove the newly added project scaffolds and revert only project configuration changes.
- No production data or external service is created.

## Approval-Sensitive Items

- No external hosting or infrastructure decision is required for this story.
- Dependency installation remains subject to project approval requirements.
