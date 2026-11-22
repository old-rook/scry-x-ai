# Scry-X-AI

Scry-X-AI is an unofficial MVP rules research assistant. It uses a Next.js frontend and a Python FastAPI backend, with planned Scryfall lookup and versioned Comprehensive Rules retrieval.

This project is not affiliated with Wizards of the Coast and does not provide official tournament rulings.

## Development

### Backend

```powershell
cd backend
python -m pip install -e ".[test]"
Copy-Item ..\.env.example ..\.env
python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000/api/v1`. `/health` is also available.

Run tests:

```powershell
cd backend
pytest
```

### Database

Set `DATABASE_URL` in the repository-root `.env` to a PostgreSQL connection URL before running migrations:

```text
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/scry_x_ai
```

Then, from `backend/`, apply or roll back the schema with Alembic:

```powershell
alembic upgrade head
alembic downgrade base
```

The initial migration creates only users, conversations, and messages. Repository and migration tests use in-memory SQLite until a PostgreSQL test instance is configured.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:3000`.

## Configuration

Copy `.env.example` to `.env`. The backend reads `APP_NAME`, `APP_ENV`, `API_V1_PREFIX`, `CORS_ORIGINS`, and `RULES_*` settings. The frontend reads `NEXT_PUBLIC_API_BASE_URL`. Rules files are stored under `backend/data/rules` by default; `RULES_STORAGE_DIR` can select another persistent local directory. `RULES_REFRESH_MODE=local` enables the in-process background refresh (every 24 hours by default). Set it to `external` to disable recurring scheduling; stale startup verification remains enabled.

Provider credentials and paid-usage configuration are future server-only settings and must never be placed in frontend environment variables.

## API

- `GET /api/v1/health`
- `GET /api/v1/cards?q=...&limit=...` (Scryfall card search; `limit` is 1–100)
- `GET /api/v1/cards/{card_id}` (normalized card detail and rulings)
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout` (Bearer token required; stateless)
- `GET /api/v1/admin/status` (admin role required)
- `GET /api/v1/admin/rules/status` (admin role required)
- `POST /api/v1/admin/rules/refresh` (admin role required; queued in the background)

Authentication uses JWT bearer tokens signed by `JWT_SIGNING_KEY`. Access tokens expire after 15 minutes. Set the signing key only through an environment variable or secret manager; never commit it or expose it in API responses/logs. Guest state remains browser-local and is not uploaded automatically.

Card lookup uses the public Scryfall API and requires no credentials. Provider timeouts, rate limits, network failures, and invalid upstream responses return safe error codes without including upstream response bodies. The health endpoint checks Scryfall availability.

## Limitations

Rules ingestion discovers the current TXT link from the official Wizards rules page, validates and indexes it, then atomically activates a versioned local copy. No database migration is used. Status reports contain only safe version/checksum/failure classifications, not raw exception or configuration data.

The local filesystem backend is not suitable for serverless or ephemeral Vercel runtimes. Deployments there need a persistent/shared rules-storage backend before using ingestion. For an external scheduler, use `RULES_REFRESH_MODE=external` and call the admin-only refresh endpoint using an existing admin bearer token managed securely by the scheduler; preserve shared persistent storage and coordinate refreshes across instances. No scheduler credential or Vercel-specific infrastructure is provided here.

AI answer generation remains unimplemented and uncoupled from ingestion. Generated explanations and integration behavior from later stories must remain source-grounded and verified against displayed card text and official rules.