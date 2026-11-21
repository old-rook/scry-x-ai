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

Set `VITE_API_BASE_URL` to a deployed API URL if it differs from `/api/v1`.

## Rules ingestion

```powershell
cd backend
python -m app.scripts.ingest_rules --source "https://official.example/comprehensive-rules.txt" --database data/rules.db
```

Ingestion validates a plausible rule count, computes a SHA-256 checksum, writes a staged database, and activates it only after the integrity checks complete. A failed update preserves the prior active database.

## Configuration

Copy `.env.example` to `.env`. The default `LLM_PROVIDER=mock` mode provides evidence-grounded explanations for supported common mechanics from a small curated rule excerpt set. To enable broader generated answers, set `LLM_PROVIDER=openai-compatible`, `LLM_API_KEY`, and `LLM_MODEL`; `LLM_BASE_URL` defaults to the OpenAI API and can point to another OpenAI-compatible endpoint. Never put provider keys in frontend configuration.

## API

- `GET /api/v1/health`
- `GET /api/v1/rules/version`
- `POST /api/v1/cards/identify`
- `POST /api/v1/judge/ask`

## Limitations

The MVP uses local lexical retrieval rather than a formal rules engine or semantic embeddings. Without an LLM provider, the backend answers supported interactions from curated rules summaries and reports insufficient evidence for unsupported topics rather than returning unrelated rules. Run the rules ingestion command to search the full Comprehensive Rules dataset. Generated explanations must be verified against the displayed card text and official rules. Card lookup also requires network access unless cached provider data is added.