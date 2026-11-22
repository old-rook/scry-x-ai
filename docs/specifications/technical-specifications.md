# Scry-X-AI Technical Specifications

## 1. Purpose

This specification defines the proposed implementation architecture and contracts for Scry-X-AI. It is based on the project instructions and the current repository state.

The repository is currently documentation-only: no application source tree or executable implementation is present. This document therefore defines a target MVP design, not documentation of an existing stack.

## 2. System Architecture

### 2.1 Target Components

- **Frontend:** Next.js, TypeScript, Tailwind CSS, and shadcn/ui.
- **Backend:** Python and FastAPI.
- **Database:** PostgreSQL for application and conversation persistence.
- **Rules store:** A locally stored, versioned, validated Comprehensive Rules dataset.
- **Card provider:** Scryfall API.
- **Rules source:** Official Wizards of the Coast Comprehensive Rules.
- **AI provider integration:** Provider-independent interface with HTTPX REST adapters for OpenRouter and Gemini.

The frontend and backend must remain independently deployable. The frontend should support Vercel; the backend must be deployable independently of the frontend host.

### 2.2 Separation of Concerns

- UI components must not contain business or rules-retrieval logic.
- FastAPI route handlers must validate requests and delegate to application services.
- Database access must remain behind repositories or a data-access layer.
- Provider-specific code must remain behind common interfaces.
- Configuration must be environment-driven.
- Business operations must be testable without HTTP or UI infrastructure.

## 3. Proposed Repository Layout

The exact package layout may evolve, but the implementation should begin with a clear separation:

```text
frontend/
  app/
  components/
  lib/
  tests/

backend/
  app/
    api/
    services/
    repositories/
    providers/
    retrieval/
    rules/
    schemas/
    core/
  tests/

docs/
  product/
  specifications/

.env.example
```

Generated databases, staged rules files, secrets, logs, dependencies, and coverage output must remain excluded from source control.

## 4. Backend API

The API should use a versioned prefix such as `/api/v1`.

### 4.1 Health

`GET /api/v1/health`

Returns service status and non-secret dependency summaries.

Possible fields:

- `status`
- `database.status`
- `scryfall.status`
- `rules.status`
- `rules.version`
- `rules.last_verified_at`
- `ai.status`

### 4.2 Card Lookup

`GET /api/v1/cards?q=...&limit=...`

Search cards through the isolated Scryfall provider adapter. `limit` defaults to 10 and is bounded from 1 to 100. Responses use the existing `CardSearchResponse`/`CardDetail` schemas.

`GET /api/v1/cards/{card_id}`

Returns normalized card details and rulings, mapping Scryfall ruling sources (`wotc` and `scryfall`) to the contract's `gatherer` and `scryfall` values respectively. The `wotc` label identifies Wizards of the Coast's official rulings, represented as `gatherer` in the existing contract. The adapter limits search requests to one every 500 ms and all other requests to one every 100 ms. Provider calls also use bounded timeouts and retries; timeout, rate limit, network, and malformed-response errors are returned without raw upstream bodies. The Scryfall dependency status in `GET /api/v1/health` is checked using the API root endpoint.

Normalized card fields (defined by the existing API schema):

- `id`
- `name`
- `mana_cost`
- `type_line`
- `oracle_text`
- `set_name`
- `rarity`
- `image_urls`
- `rulings`
- `source`
- `source_updated_at`

### 4.3 Answer Generation

`POST /api/v1/answers`

Request:

```json
{
  "conversation_id": "optional UUID",
  "question": "What happens when...",
  "card_names": ["Optional normalized card names"],
  "guest": true
}
```

Response:

```json
{
  "answer_id": "UUID",
  "conversation_id": "optional UUID",
  "verdict": "string",
  "explanation": "string",
  "comprehensive_rules": [],
  "card_rulings": [],
  "additional_considerations": [],
  "model": "provider-neutral model identifier",
  "evidence_status": "complete | partial | insufficient",
  "disclaimer": "string"
}
```

Response arrays must contain structured source objects, not free-text citation names only.

### 4.4 Conversations

Authenticated APIs should support:

- `GET /api/v1/conversations`
- `POST /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`
- `DELETE /api/v1/conversations/{conversation_id}`

Guest conversations must be stored only in browser storage unless the user explicitly consents to synchronization.

## 5. Citation Data Contracts

### 5.1 Comprehensive Rule

```json
{
  "section": "704.5",
  "title": "Optional title",
  "text": "Official rules text",
  "source_url": "Official source URL",
  "checksum": "SHA-256 of source document",
  "ruleset_version": "Version or publication identifier"
}
```

### 5.2 Card Ruling

```json
{
  "oracle_card_id": "Scryfall card ID",
  "card_name": "Card name",
  "published_at": "ISO 8601 date",
  "comment": "Official ruling text",
  "source": "scryfall | gatherer",
  "source_url": "Optional source URL"
}
```

The answer pipeline must reject citations not present in the retrieved evidence set.

## 6. Data Model

The PostgreSQL schema should begin with the minimum entities required by MVP:

- `users`
- `conversations`
- `messages`
- `answer_sources`
- `provider_usage`
- `provider_failures`
- `rules_versions`
- `rules_refresh_operations`
- `card_cache` if caching is implemented

Schema changes require explicit human approval.

### 6.0 Phase 1 Persistence Baseline

The approved P1-S03 migration establishes only `users`, `conversations`, and `messages`. It uses SQLAlchemy 2, Alembic, and Psycopg 3. The current schema is intentionally minimal:

- `users`: UUID primary key, creation/update timestamps, local email and password hash, and `user`/`admin` role.
- `conversations`: UUID primary key, owning user UUID, title, creation timestamp, and update timestamp.
- `messages`: UUID primary key, conversation UUID, `user`/`assistant` role, content, and creation timestamp.

The approved P1-S07 addition persists provider usage/failure classifications in `provider_audit`; it deliberately excludes prompts, responses, credentials, and raw payloads. Until a PostgreSQL test instance is available, repository and migration tests use in-memory SQLite; PostgreSQL integration testing remains outstanding.

### 6.1 Users

The eventual user record may include:

- `id`
- `email` or an approved provider identity
- `role`
- `created_at`
- `updated_at`

Authentication identity and role fields are not present in the P1-S03 baseline. Admin role checks must be enforced server-side when authentication is implemented.

### 6.2 Conversations

- `id`
- `user_id`
- `title`
- `created_at`
- `updated_at`

### 6.3 Messages

- `id`
- `conversation_id`
- `role`
- `content`
- `model_identifier`
- `evidence_status`
- `created_at`

### 6.4 Answer Sources

- `id`
- `message_id`
- `source_type`
- `source_reference`
- `source_url`
- `retrieved_at`

### 6.5 Rules Versions

- `id`
- `version`
- `publication_date`
- `verification_status`
- `checksum`
- `source_url`
- `activated_at`
- `verified_at`
- `failure_reason`

No version may be activated until validation succeeds.

## 7. Rules Ingestion and Storage

### 7.1 Source Verification

The backend discovers the current TXT download link from `https://magic.wizards.com/en/rules`; dated download URLs must not be hardcoded. The TXT document is fetched and parsed using the standard library, with HTTP handled by the existing `httpx` dependency.

The local MVP stores immutable, versioned source and parsed/indexed files plus one atomically replaced active state manifest containing both the active version and refresh status. This avoids separate status/manifest commits. It does not modify the database schema. `RULES_REFRESH_MODE=local` runs an in-process background refresh at an interval of at most 24 hours. `RULES_REFRESH_MODE=external` disables recurring scheduling, but startup still triggers verification if no successful verification exists or it is older than 24 hours. Refresh requests run asynchronously and concurrent ingestion is guarded within the application process.

An administrator may inspect `GET /api/v1/admin/rules/status` and queue a refresh with `POST /api/v1/admin/rules/refresh`. Both routes require the existing admin role. Status exposes the latest known official version separately from the active verified local version and includes classified failure codes rather than exception payloads.

### 7.2 Download and Validation

The refresh pipeline must:

1. Discover the current TXT URL from the official rules page.
2. Validate UTF-8 encoding, document title and effective date.
3. Verify a plausible numbered-rule count and required sections.
4. Compute a SHA-256 checksum over the downloaded bytes.
5. Parse rules into a locally persisted lexical index.
6. Activate the staged ruleset only after all validation succeeds.
7. Preserve the previous active manifest and data on every failure.
8. Record source/version/publication date/checksum/status/verification times and a safe failure classification.

The filesystem storage backend requires persistent storage. It is not suitable for a serverless or ephemeral Vercel runtime without replacing that backend. An external scheduler must authenticate to the admin refresh endpoint using an existing admin bearer token kept in a secret manager, and requires persistent storage shared with the backend. This MVP adds no scheduler credential, service account, or Vercel-specific infrastructure.

### 7.3 Retrieval

The MVP may use targeted lexical or hybrid retrieval. Semantic embeddings are not required for MVP and require a separate technical decision.

Retrieval must:

- Identify relevant card names and rule concepts.
- Retrieve only the smallest useful set of rule sections.
- Avoid sending the complete rules document to the model.
- Preserve source text and source references in the evidence context.
- Return an insufficient-evidence result when relevance cannot be established.

The rules retrieval data structure must remain replaceable if a later semantic retrieval implementation is approved.

## 8. Scryfall Integration

Scryfall calls must be isolated behind a card-provider interface.

Requirements:

- Normalize card and ruling responses.
- Apply timeouts and bounded retries.
- Use cache-backed lookups when feasible.
- Cache only data appropriate for reuse and include retrieval/update timestamps.
- Return explicit provider or rate-limit errors.
- Keep card-provider-specific response fields out of core business logic.

Scryfall is a retrieval provider. Oracle text and official ruling distinctions must remain visible in API and UI responses.

## 9. AI Provider Abstraction

### 9.1 Interface

The provider interface should expose operations for answer generation and provider health, for example:

- `generate_answer(request, evidence, conversation_context)`
- `health()`

Provider implementations must not leak provider SDK types into route handlers or application services.

### 9.2 Configuration

Configuration uses server-only environment variables and includes:

- Primary provider/model and optional fallback provider/model.
- Explicit `free`/`paid` classification for every configured model.
- Request timeout.
- Maximum bounded retries.
- Exponential backoff settings.
- Paid usage enabled flag.
- Monthly reported-cost limit (maximum USD 5).
- Server-side API keys.

Provider API keys must remain server-side and must never be included in frontend variables or API responses.

No provider or model identifier is selected by default; operators supply these identifiers and must verify the model's current pricing and availability. Paid models are blocked unless `LLM_PAID_ENABLED=true`, and enabling the gate requires a positive configured monthly cap no greater than USD 5. `LLM_PAID_MINIMUM_REMAINING_USD` defaults to USD 1.00, must be positive, and cannot exceed a positive configured monthly cap. Before a paid generation, the backend atomically and exclusively reserves the entire remaining budget (`effective cap - settled spend`) in a per-month database row using a conditional update/upsert supported by SQLite and PostgreSQL. The reservation is held across all paid retries/fallbacks for the generation. A valid provider-reported cost settles it and makes the newly remaining amount available to a later sequential call if it meets the minimum threshold. Missing, malformed, negative, or otherwise untrusted cost consumes/locks the remaining monthly app budget while the usable generation result is still returned. Paid provider errors with unknown possible cost also fail closed. Reservations survive process crashes and are not automatically expired or released. This prevents concurrent generations from independently reserving the same budget, but is not an absolute billing guarantee: provider cost is reported only after a request, so one individual request can overrun the remaining budget before settlement. Provider-side limits are needed for a true external spending cap. Provider credentials use `SecretStr`.

The health summary contains only configured provider/model identifiers and local configuration/credential readiness (not a live upstream connectivity check). Usage/failure audit records contain provider, model, cost tier, time, outcome, error class, token counts, and provider-reported cost; prompts, responses, credentials, and raw upstream bodies are never stored in that audit. Monthly budget totals come from paid-tier reservations/settlements, not free-tier audit rows.

### 9.3 Failover

Provider errors must be classified and audited:

- Timeout.
- Rate limit.
- Authentication or authorization.
- Provider unavailable.
- Invalid provider response.
- Context or request too large.
- Unknown provider error.

Eligible timeout, rate-limit, and provider-availability errors may trigger bounded exponential retries and then the configured fallback. Authentication, configuration, context-too-large, invalid-request, and malformed-response errors must not fail over. The same complete neutral request (including conversation/evidence context) is passed to the fallback. If audit persistence fails, generation must fail rather than return an unaudited success or silently proceed to fallback.

## 10. Answer Pipeline

The answer pipeline must:

1. Validate and normalize the question.
2. Identify explicit card names and relevant state details.
3. Request clarification for materially missing information.
4. Retrieve relevant Oracle text and card rulings.
5. Retrieve relevant Comprehensive Rules sections.
6. Package the evidence and conversation context.
7. Generate a structured answer.
8. Parse the provider response.
9. Validate citation references against the retrieved evidence.
10. Reject unsupported citations or evidence claims.
11. Persist the answer and source references when authorized.
12. Record model and usage information.

The provider is not allowed to introduce source references that are absent from the retrieved evidence set.

If evidence is partial or missing, the result must qualify the answer or return insufficient evidence rather than supplying unrelated rules.

## 11. Authentication and Authorization

The MVP should support a provider-neutral authentication design with server-side sessions or JWTs, subject to final approval.

Every authenticated conversation and message endpoint must verify ownership.

Admin endpoints must require an admin role and must not return:

- API keys.
- Access tokens.
- Raw provider configuration secrets.
- Private environment values.

Guest content must not be sent to the backend for persistence unless synchronization is explicitly initiated and authorized.

## 12. Frontend Architecture

### 12.1 Core Views

- Rules Q&A workspace.
- Conversation history.
- Card lookup and card detail panel.
- Card-ruling and Oracle-text panel.
- Rules citation panel.
- Settings/account view.
- Restricted administrator dashboard.

### 12.2 State

Guest conversations should use browser-local storage with explicit versioning and bounded retention.

Registered conversations should use server persistence through typed API clients.

UI components should not call provider APIs directly or store secrets.

### 12.3 API Contract

Frontend API types must match backend Pydantic schemas or an independently reviewed generated contract. Contract drift must be caught by integration or component tests.

## 13. Observability

The backend should log structured, non-sensitive events for:

- Provider requests and classified failures.
- Model and token usage.
- Fallback attempts.
- Rules refresh operations.
- Scryfall failures.
- Database failures.
- Authentication failures and authorization denials.

Secrets and raw private provider payloads must not be logged.

## 14. Configuration

Server configuration should use environment variables and include separate settings for:

- Database URL.
- Scryfall endpoint and credentials if later required.
- Official rules source URL.
- Rules refresh interval.
- Provider configuration.
- Model configuration.
- Paid usage settings.
- Spending limits.
- Authentication configuration.
- Allowed frontend origins.

The project should retain a non-secret `.env.example` template only.

## 15. Testing Requirements

### 15.1 Unit Tests

Cover:

- Question normalization.
- Citation validation.
- Rules refresh validation.
- Provider error classification.
- Retry and fallback decisions.
- Ownership and authorization helpers.

### 15.2 Integration Tests

Cover:

- Database repositories.
- Scryfall adapter behavior.
- Provider adapter behavior.
- Rules ingestion and activation.
- Frontend API contracts.

### 15.3 Backend API Tests

Cover:

- Health endpoints.
- Card lookup.
- Answer generation.
- Guest and registered conversation behavior.
- Admin route authorization.
- Rules refresh endpoints.

### 15.4 Frontend Component Tests

Cover:

- Structured answer rendering.
- Citation rendering.
- Clarification and insufficient-evidence states.
- Light and dark themes.
- Conversation history behavior.
- Card and ruling panels.

### 15.5 End-to-End Tests

Cover:

- Guest Q&A flow.
- Card lookup flow.
- Follow-up conversation flow.
- Registered conversation synchronization and ownership.
- Admin restricted access.

### 15.6 Rules Evaluation

Maintain a curated set of verified MTG questions. Evaluate answers separately for:

1. Factual accuracy.
2. Rules reasoning.
3. Citation existence.
4. Citation relevance.
5. Uncertainty handling.
6. Consistency.

### 15.7 Regression and Failure Tests

Include:

- Rules refresh success and failed-update rollback.
- Provider timeout and failover.
- Provider rate limiting.
- Scryfall/API failures.
- Authentication and authorization failures.
- Corrupt or malformed rules downloads.
- Invalid or hallucinated AI citations.

## 16. Deployment

The frontend and backend must remain independently deployable.

The backend deployment must support:

- Environment-only configuration.
- Database migrations.
- Health checks.
- Startup rules freshness checks and either a persistent local scheduler or an external scheduler.
- Persistent rules storage; ephemeral/serverless filesystems require a replacement storage backend.
- Secret injection without source-control storage.

The frontend deployment must not contain provider API keys or paid-model configuration.

## 17. Implementation Order

### Phase 1: Foundation

1. Create the frontend and backend project structures.
2. Implement typed API contracts.
3. Configure database access.
4. Implement authentication and authorization foundations.
5. Implement Scryfall adapter.
6. Implement rules ingestion and version management.
7. Implement provider abstraction and failover configuration.

### Phase 2: Core Rules Assistant

1. Implement card and rule retrieval.
2. Implement structured answer generation.
3. Validate citation output.
4. Implement clarification and insufficient-evidence behavior.
5. Implement follow-up context.

### Phase 3: User Experience

1. Build the rules workspace.
2. Build card and citation panels.
3. Implement guest history.
4. Implement registered conversation history.
5. Add responsive light/dark themes.

### Phase 4: Administration and Quality

1. Build the restricted admin dashboard.
2. Add model usage and failure monitoring.
3. Complete MTG answer evaluation.
4. Complete rules and security regression suites.
5. Validate deployment readiness.

Each implementation story should have scoped acceptance criteria and independent QA where significant.
