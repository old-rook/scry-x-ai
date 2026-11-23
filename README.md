# Scry-X-AI

Scry-X-AI is an unofficial MVP rules research assistant. It uses a Next.js frontend and a Python FastAPI backend, with Scryfall lookup and versioned Comprehensive Rules retrieval.

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

The guest chat keeps up to five recent conversations in versioned browser-local storage; it does not sync them to an account or persist them on the backend. Follow-up requests include only the latest six bounded user/assistant turns. Development defaults to `http://localhost:8000/api/v1`; set `NEXT_PUBLIC_API_BASE_URL` when the backend uses another address.

## Free-tier POC deployment

The POC can use a Vercel frontend, a Railway Free FastAPI service with a Railway volume, and Supabase Free PostgreSQL. Railway Free can sleep and stops services when its monthly allowance is exhausted; therefore the in-process scheduler cannot guarantee a rules check every 24 hours. Supabase Free can pause after inactivity. This setup is for a POC, not production; check current limits and pricing before provisioning.

1. Create a dedicated Supabase Free project. This application uses direct PostgreSQL access, not the Supabase Data API. Before creating application tables, disable the Data API for this dedicated project and verify it is disabled. The existing Alembic migrations do not configure Supabase row-level security or grants. Do not disable the Data API on a shared project without assessing other applications.
2. Obtain the PostgreSQL connection string privately from Supabase. For an IPv4-only backend, use the session pooler. For SQLAlchemy, use the `postgresql+psycopg://` scheme and retain the host, port, username, and SSL options supplied by Supabase. Never commit or share the connection string.
3. In Railway, create a Free service from this repository and set its root directory to `backend`. Set `RAILPACK_INSTALL_CMD` to `python -m pip install --target /app/vendor .` and `PYTHONPATH` to `/app/vendor` so the installed dependencies are available at runtime. Set the service start command to:

   ```sh
   /bin/sh -c 'exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"'
   ```

   Attach a Railway volume at `/data`, generate a public domain, and set these backend variables:

   ```text
   APP_ENV=production
   RULES_STORAGE_DIR=/data/rules
   CARD_CATALOG_PATH=/data/card-names.json
   RULES_REFRESH_MODE=local
   LLM_PAID_ENABLED=false
   ```

   Set `DATABASE_URL` privately to the Supabase connection string and `CORS_ORIGINS` to the exact HTTPS Vercel frontend origin. For multiple origins, separate them with commas; preview origins must be explicitly permitted. Configure an explicitly classified free AI model and its provider key only after verifying its current eligibility. A missing AI configuration prevents answer generation.
4. The database schema must be initialized with the existing Alembic migrations before database-backed features work. Obtain approval for the schema change and check the target database and backups before running `alembic upgrade head` from `backend` with `DATABASE_URL` securely available. Do not run migrations against an existing shared database without reviewing their impact.
5. In Vercel, deploy the repository-root project using the frontend-only service in `vercel.json`. Set `NEXT_PUBLIC_API_BASE_URL` to the Railway HTTPS URL ending in `/api/v1` in the Vercel environment settings before redeploying. This value is embedded at build time; the Vercel build fails if it is missing or is not a public HTTPS URL. The FastAPI backend is deployed separately on Railway.
6. Check Railway's `/api/v1/health`, `/api/v1/cards?q=Lightning%20Bolt&limit=1`, and `/api/docs`, then test a guest question from Vercel. Health can remain degraded until the database is reachable and the rules are successfully verified. Check the rules status after startup; do not treat an unverified ruleset as current.

## Vercel frontend-only deployment

The root [`vercel.json`](./vercel.json) configures one Vercel service: the Next.js frontend. All requests are routed to that frontend service; no FastAPI backend is deployed to Vercel. The frontend calls the separately deployed Railway backend using `NEXT_PUBLIC_API_BASE_URL`.

Set `NEXT_PUBLIC_API_BASE_URL` to the Railway public HTTPS API base ending in `/api/v1` for every Vercel environment you deploy. This value is public browser configuration, so never put credentials or keys in it. Next.js embeds it at build time, so redeploy after changing it. The frontend-only Vercel build rejects missing, same-origin, local, or non-HTTPS API URLs.

Configure the backend's database and secrets on Railway, not in Vercel. The backend also needs persistent storage for its rules and card-name catalog. Configure `CORS_ORIGINS` on Railway to include the Vercel frontend origin. After deployment, verify the frontend loads, the Railway `/api/v1/health` endpoint responds, and a guest question works. A real AI request may incur provider charges.

The existing `.env.example` contains paid-model settings with `LLM_PAID_ENABLED=true`; do not copy it unchanged into production. Keep paid usage disabled unless explicitly approved, and keep all AI keys and budget settings on the backend.

## Configuration

Copy `.env.example` to `.env`. The backend reads `APP_NAME`, `APP_ENV`, `API_V1_PREFIX`, `CORS_ORIGINS`, `RULES_*`, and optional server-only `LLM_*` settings. The frontend reads `NEXT_PUBLIC_API_BASE_URL`. Rules files are stored under `backend/data/rules` by default; `RULES_STORAGE_DIR` can select another persistent local directory. `RULES_REFRESH_MODE=local` enables the in-process background refresh (every 24 hours by default). Set it to `external` to disable recurring scheduling; stale startup verification remains enabled.

AI provider setup is opt-in. Configure `LLM_PRIMARY_PROVIDER`/`LLM_PRIMARY_MODEL` and optionally one fallback with the provider/model identifiers selected by the operator. Every configured model must be explicitly classified as `free` or `paid`; confirm current pricing and eligibility with the provider rather than assuming a model is free. API keys use `LLM_OPENROUTER_API_KEY`, `LLM_GEMINI_API_KEY`, or `LLM_OPENAI_API_KEY` and must remain server-side. `LLM_OPENAI_BASE_URL` configures the OpenAI-compatible HTTPS endpoint; it defaults to `https://api.openai.com/v1`. The health availability value reflects local configuration/credential readiness, not a live upstream connectivity check.

The current local answer configuration uses OpenAI `gpt-4o-mini`, classified as paid. Set the API key privately in `.env` or a secret manager; never put it in frontend variables or source control. The `.env` file uses these model settings:

```text
LLM_PRIMARY_PROVIDER=openai
LLM_PRIMARY_MODEL=gpt-4o-mini
LLM_PRIMARY_MODEL_COST=paid
LLM_OPENAI_BASE_URL=https://openai.vocareum.com/v1
LLM_PAID_ENABLED=true
LLM_MONTHLY_CAP_USD=20
LLM_PAID_MINIMUM_REMAINING_USD=5
LLM_OPENAI_PRICING_MODEL=gpt-4o-mini
LLM_OPENAI_INPUT_PRICE_PER_MILLION_USD=0.15
LLM_OPENAI_CACHED_INPUT_PRICE_PER_MILLION_USD=0.075
LLM_OPENAI_OUTPUT_PRICE_PER_MILLION_USD=0.60
```

Set `LLM_OPENAI_API_KEY` privately. The configured base URL must provide the OpenAI Chat Completions API over HTTPS. Direct OpenAI chat responses provide token counts rather than dollar costs, so the backend estimates cost using `LLM_OPENAI_PRICING_MODEL` and the configurable input, cached-input, and output rates in `.env`. The initial `gpt-4o-mini` standard rates are USD 0.15, 0.075, and 0.60 per million tokens respectively; verify current [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) and update all rates when changing model or pricing. If reliable usage counts are absent, budget accounting fails closed.

Paid models are blocked unless `LLM_PAID_ENABLED=true`; enabling paid usage also requires a positive `LLM_MONTHLY_CAP_USD` no greater than USD 20. `LLM_PAID_MINIMUM_REMAINING_USD` defaults to USD 1.00 and must be positive and, when a positive monthly cap is configured, no greater than that cap. Before paid generation, the backend atomically reserves the entire remaining budget (`effective cap - settled spend`) exclusively in the database, shared across processes. A later sequential generation may reserve the newly remaining amount after the previous reservation settles, provided it meets the minimum-remaining threshold. Unknown/malformed/negative cost consumes and blocks the remaining app budget for that month, while a usable response is still returned. Reservations left by a crash remain held for the rest of that month.

The app budget is **not an absolute billing guarantee**: provider cost is reported only after a request, so one request can cost more than the remaining budget before the backend can settle it; provider reports, adjustments, and billing periods may also differ. Set a provider-side spending limit for an external billing cap. Do not enable paid models without reviewing their pricing and operational limits.

## API

- `GET /api/v1/health`
- `GET /api/v1/cards?q=...&limit=...` (Scryfall card search; `limit` is 1–100)
- `GET /api/v1/cards/{card_id}` (normalized card detail and rulings)
- `POST /api/v1/answers` (guest-only, evidence-grounded answer; no conversation persistence)
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout` (Bearer token required; stateless)
- `GET /api/v1/admin/status` (admin role required)
- `GET /api/v1/admin/rules/status` (admin role required)
- `POST /api/v1/admin/rules/refresh` (admin role required; queued in the background)

Authentication uses JWT bearer tokens signed by `JWT_SIGNING_KEY`. Access tokens expire after 15 minutes. Set the signing key only through an environment variable or secret manager; never commit it or expose it in API responses/logs. Guest state remains browser-local and is not uploaded automatically.

Card lookup uses the public Scryfall API and requires no credentials. Provider timeouts, rate limits, network failures, and invalid upstream responses return safe error codes without including upstream response bodies. The health endpoint aggregates database, Scryfall, Comprehensive Rules, and AI status. It distinguishes the latest known official rules version from the latest verified local version and reports configured AI provider/model identifiers and availability only; it never includes API keys, source URLs, or raw provider errors.

The answer endpoint sends only a bounded question, up to six recent user/assistant turns supplied by the browser, and bounded retrieved evidence to the configured AI route. Context is untrusted and is not logged, synced, or stored; `guest=false` is rejected. Automatic deterministic card-name extraction requires an exact Scryfall name match. Retrieval is bounded keyword/explicit-rule matching (not semantic search); only fresh, verified, non-superseded rules are eligible. Model output must be strict JSON and every citation is checked against the evidence retrieved for that request. Malformed output, unknown citations, or no usable evidence return a safe insufficient-evidence response with no generated citations; malformed output is not regenerated. This POC does not implement conversation synchronization, answer-quality guarantees, or official rulings. The existing `card_names` request field remains accepted for compatibility; card extraction is automatic.

## Limitations

Rules ingestion discovers the current TXT link from the official Wizards rules page, validates and indexes it, then atomically activates a versioned local copy. No database migration is used. Status reports contain only safe version/checksum/failure classifications, not raw exception or configuration data.

The local filesystem backend is not suitable for serverless or ephemeral Vercel runtimes. Deployments there need a persistent/shared rules-storage backend before using ingestion. For an external scheduler, use `RULES_REFRESH_MODE=external` and call the admin-only refresh endpoint using an existing admin bearer token managed securely by the scheduler; preserve shared persistent storage and coordinate refreshes across instances. No scheduler credential or Vercel-specific infrastructure is provided here.

The answer API and guest chat UI are implemented as a POC; registered conversation synchronization is not implemented. Guest conversations remain browser-owned. Answers can be incomplete because retrieval is deliberately bounded and keyword-based; users should check cited text and the current official rules.