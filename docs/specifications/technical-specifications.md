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
- **AI provider integration:** Provider-independent interface with OpenRouter as the initial implementation.

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

`GET /api/v1/cards`

Search cards by name.

Query parameters:

- `q: string` — card name or search text
- `limit: integer` — bounded result count

`GET /api/v1/cards/{card_id}`

Returns normalized card details and card-specific rulings.

Possible normalized fields:

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

### 6.1 Users

At minimum:

- `id`
- `email` or an approved provider identity
- `role`
- `created_at`
- `updated_at`

Admin role checks must be enforced server-side.

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

A scheduled task must verify official rules freshness at least every 24 hours and during startup when the active verification is stale.

An administrator may trigger manual verification or refresh.

### 7.2 Download and Validation

The refresh pipeline must:

1. Fetch the official rules source.
2. Stream the downloaded content into a staging file or database.
3. Validate encoding and basic document structure.
4. Verify a plausible rule count and required section patterns.
5. Compute a SHA-256 checksum.
6. Parse rules into an indexed representation.
7. Run integrity checks.
8. Activate the staged ruleset only after success.
9. Preserve the previous active ruleset on every failure.
10. Record update status and failure details.

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

Configuration must include:

- Provider name.
- Primary model.
- Ordered fallback models/providers.
- Request timeout.
- Maximum bounded retries.
- Exponential backoff settings.
- Paid usage enabled flag.
- Spending limit.
- Server-side API keys.

Provider API keys must remain server-side and must never be included in frontend variables or API responses.

Free models are the default. `LLM_PAID_ENABLED=true` must not occur unless explicitly configured; all paid behavior must remain gated and audited.

### 9.3 Failover

Provider errors must be classified and logged:

- Timeout.
- Rate limit.
- Authentication or authorization.
- Provider unavailable.
- Invalid provider response.
- Context or request too large.
- Unknown provider error.

Eligible timeout, rate-limit, and provider-availability errors may trigger bounded fallback. Authentication/configuration errors should not trigger retries against unrelated providers.

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
- Scheduled or startup rules freshness checks.
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
