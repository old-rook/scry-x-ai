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

Copy `.env.example` to `.env`. The foundation backend reads `APP_NAME`, `APP_ENV`, `API_V1_PREFIX`, and `CORS_ORIGINS`. The frontend reads `NEXT_PUBLIC_API_BASE_URL`.

Provider credentials and paid-usage configuration are future server-only settings and must never be placed in frontend environment variables.

## API

- `GET /api/v1/health`

## Limitations

The MVP foundation does not yet implement rules ingestion, card lookup, or AI answer generation. Generated explanations and integration behavior from later stories must remain source-grounded and verified against displayed card text and official rules.