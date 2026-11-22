# Scry-X-AI

Scry-X-AI is an unofficial MVP rules research assistant. It combines Scryfall card lookup, a versioned SQLite Comprehensive Rules dataset, lexical retrieval, and a structured, citation-validating answer pipeline.

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

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Set the Next.js API base URL to a deployed backend URL if it differs from `/api/v1`. Keep provider credentials exclusively in backend environment variables.

## Rules ingestion

```powershell
cd backend
python -m app.scripts.ingest_rules --source "https://official.example/comprehensive-rules.txt" --database data/rules.db
```

Ingestion validates a plausible rule count, computes a SHA-256 checksum, writes a staged database, and activates it only after the integrity checks complete. A failed update preserves the prior active database.

## Configuration

Copy `.env.example` to `.env`. Configure the provider-independent backend with `LLM_PROVIDER=openrouter`, a server-side provider API key, a primary model, and optional ordered fallback models. Free models are the default. Paid provider usage must remain disabled unless `LLM_PAID_ENABLED=true` is set explicitly and a spending limit is configured. Never put provider keys or paid-usage configuration in frontend environment variables.

## API

- `GET /api/v1/health`
- `GET /api/v1/rules/version`
- `POST /api/v1/cards/identify`
- `POST /api/v1/judge/ask`

## Limitations

The MVP uses local lexical retrieval rather than a formal rules engine or semantic embeddings. Without an LLM provider, the backend answers supported interactions from curated rules summaries and reports insufficient evidence for unsupported topics rather than returning unrelated rules. Run the rules ingestion command to search the full Comprehensive Rules dataset. Generated explanations must be verified against the displayed card text and official rules. Card lookup also requires network access unless cached provider data is added.