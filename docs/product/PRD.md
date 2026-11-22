# Scry-X-AI Product Requirements Document

## 1. Document Purpose

This document defines the MVP requirements for Scry-X-AI, an unofficial Magic: The Gathering rules and card-interaction assistant.

Scry-X-AI is not affiliated with or endorsed by Wizards of the Coast. It is a rules research tool and must not present generated explanations as official tournament rulings.

## 2. Product Vision

Build a trustworthy, data-first MTG rules reference that helps beginners, experienced players, and judges understand card interactions through:

- Direct natural-language rules answers.
- Authoritative Oracle text and card-specific rulings.
- Relevant Comprehensive Rules citations.
- Clear separation between retrieved evidence and AI interpretation.
- Follow-up conversations that preserve the relevant rules context.

Rules accuracy and citation validity take priority over fluent or confident-sounding answers.

## 3. Target Users

### 3.1 Casual players

- Need plain-language answers.
- May not know the names of relevant rules sections.
- Need uncertainty and missing-context explanations.

### 3.2 Experienced players

- Need precise interaction analysis.
- Need exact card text, timestamps, zones, and relevant rule sections.
- May ask about multiple cards or unusual game states.

### 3.3 Judges and rules researchers

- Need concise, auditable evidence.
- Need verifiable citations and direct access to source text.
- Must be able to distinguish Oracle text, official rulings, and generated interpretation.

### 3.4 Administrators

- Need to monitor application, database, provider, and ruleset health.
- Need to refresh or verify the Comprehensive Rules dataset.
- Must not receive secret or private provider configuration values.

## 4. MVP Scope

### 4.1 Rules Q&A

The application must provide:

1. A natural-language question field.
2. A direct verdict answer.
3. A supporting explanation.
4. Relevant Comprehensive Rules citations.
5. Relevant card rulings when applicable.
6. Additional considerations for important edge cases.
7. A clarification request when the game state or card names are insufficient.

The answer interface must use this response structure:

1. **Verdict**
2. **Explanation**
3. **Comprehensive Rules**
4. **Card rulings**
5. **Additional considerations**

### 4.2 Card lookup

The application must allow users to:

- Search for cards by name.
- View the current Oracle name and Oracle text.
- View card images and basic card metadata when provided by Scryfall.
- Open or view relevant card-specific rulings.
- Reuse identified cards in rules questions.

Oracle text is the authoritative current card text. Scryfall is a retrieval provider, not the replacement authority.

### 4.3 Card interaction analysis

The system must identify relevant cards and rules from a question, retrieve supporting evidence, and explain interactions involving multiple cards.

Answers must:

- Preserve the distinction between card text, rulings, and AI interpretation.
- Identify relevant edge cases.
- Avoid invented card names, Oracle text, rulings, or rule citations.
- Disclose insufficient evidence instead of guessing.

### 4.4 Rules citations

The system must:

- Link or reference applicable Comprehensive Rules sections.
- Link or reference applicable Scryfall/Gatherer card rulings.
- Verify citation existence against retrieved source data.
- Include only citations relevant to the generated answer.
- Never fabricate citations.

### 4.5 Conversation history

Guest users:

- May use rules Q&A and card lookup without registration.
- May retain conversation history locally in the browser.
- Must not upload guest conversations automatically.
- Must receive a consent action if synchronization is offered.

Registered users:

- May persist conversation history in PostgreSQL.
- May access history across devices.
- May access only their own conversations.

### 4.6 Follow-up questions

The application must support follow-up questions within an existing conversation while preserving relevant context such as:

- Previously identified cards.
- Previously stated game zones and states.
- Prior conclusions and citations.
- Any clarification supplied by the user.

The system must ask for missing information when context remains ambiguous.

### 4.7 Administrator dashboard

Administrators must be able to view:

- Backend health.
- Database health.
- External API health.
- Active AI provider and model.
- Configured fallback providers/models and status.
- AI timeout, rate-limit, and failure counts.
- Model usage and estimated cost when available.
- Comprehensive Rules document version and verification status.
- Last successful official verification.
- Manual rules refresh status.

API keys and private configuration values must never be exposed to the frontend.

## 5. External Sources and Authority

The source hierarchy is:

1. Comprehensive Rules — general game rules authority.
2. Oracle text — authoritative current card text.
3. Scryfall/Gatherer card rulings — card-specific clarification.
4. Official Wizards sources — authoritative source verification.

Community discussions and unofficial third-party explanations are not authoritative sources.

## 6. Comprehensive Rules Freshness

The backend must:

- Check the official source at least every 24 hours.
- Check freshness during startup when the last successful verification is more than 24 hours old.
- Support administrator-triggered manual refresh.
- Download and validate updates before activation.
- Preserve the previous valid ruleset if an update fails.
- Record document version, publication date, verification date, checksum, and update status.
- Display separate information for the latest successfully verified local ruleset and the latest known official ruleset.
- Disclose when freshness cannot be confirmed.
- Never claim that the local ruleset is current after a failed verification.

## 7. AI Provider Requirements

The backend must use a provider-independent AI integration interface.

- OpenRouter is the initial provider.
- Gemini may be supported as an alternative provider.
- Primary and fallback models/providers must be configurable.
- Free models are the default.
- Paid usage must remain disabled unless explicitly enabled in server configuration.
- A paid request must never occur silently.
- If paid usage is enabled, support spending limits and usage monitoring.
- Model identifiers must not be hardcoded throughout application code.
- Preserve retrieved context when switching models.
- Apply bounded retries and exponential backoff.
- Fail over for eligible timeouts, rate limits, and provider errors.
- Classify and log provider failures.
- Record the model that generated each answer.

## 8. UX and Design Requirements

- Use a purpose-built MTG rules interface, not a generic chatbot wrapper.
- Prefer data-first layouts and compact, readable information density.
- Show the most useful answer and source information without excessive navigation.
- Support card and rules references in structured panels.
- Present citations clearly and distinguish source evidence from interpretation.
- Use consistent typography and spacing.
- Support responsive desktop and mobile layouts.
- Support light and dark themes.
- Default to dark mode.
- Use an MTG-inspired visual language without excessive gradients, glow, animation, oversized cards, or empty whitespace.
- Maintain accessible keyboard navigation, labels, focus states, and sufficient contrast.

## 9. Functional Acceptance Criteria

The MVP is complete when:

1. A guest can submit a rules question and receive a structured answer or a clarification request.
2. Unsupported interactions are not answered from unrelated rules or unsupported evidence.
3. Every displayed Comprehensive Rules citation exists in the retrieved rules data.
4. Every displayed card ruling exists in the retrieved card-ruling data.
5. Card lookup returns current Oracle text and relevant rulings through Scryfall.
6. Guest history remains local and is not uploaded without consent.
7. Registered users can persist and retrieve only their own conversations.
8. Follow-up questions preserve relevant earlier context.
9. An administrator can inspect provider, service, database, and rules freshness status.
10. Rules refresh preserves the prior valid ruleset after a failed update.
11. Paid provider usage is disabled by default.
12. The answer UI exposes retrieved evidence separately from generated interpretation.

## 10. Non-Functional Requirements

### Accuracy

- Be definitive only when authoritative evidence supports a clear conclusion.
- Qualify incomplete or conflicting evidence.
- Ask for clarification rather than guessing.
- Treat provider output as untrusted and validate citations and factual structure.

### Reliability

- External Scryfall, rules-source, database, and provider failures must be handled explicitly.
- Provider failover must be bounded and observable.
- A prior valid ruleset must remain usable after refresh failures.

### Security and privacy

- Authentication and authorization must protect registered conversations.
- Secrets must remain server-side.
- Guest data must stay in the browser unless synchronization is explicitly authorized.
- Personal data collection must remain minimal.
- Administrators must not be able to view secret values through the dashboard or APIs.

### Performance

- Card lookup and cached rules retrieval should provide a responsive user experience.
- Retrieval should avoid sending an entire Comprehensive Rules document to the AI provider.
- Heavy ingestion and refresh work must not block normal request handling.

### Accessibility

- Core flows must support keyboard use and screen-reader navigation.
- Status and error messages must be visible and announced where appropriate.
- Visual state must not be conveyed by color alone.

## 11. Explicitly Out of Scope for MVP

- Deck analysis.
- Unapproved external integrations.
- Unapproved premium services.
- Competitive or official tournament-ruling certification.
- Full analytics or moderation platforms.
- A formal MTG rules engine.
- Semantic embeddings or vector retrieval unless introduced by a separately approved technical decision.
- Features that significantly expand scope without approval.

## 12. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Stale Comprehensive Rules | Scheduled and startup verification, freshness status, manual refresh |
| Hallucinated citations | Restricted retrieval, citation validation, and insufficient-evidence responses |
| Incorrect card state interpretation | Clarification prompts and explicit capture of zones, timestamps, and game actions |
| Provider outage or rate limiting | Configurable fallback models, bounded retries, and classified error logging |
| Unexpected paid usage | Server-only configuration, disabled-by-default paid mode, and spending limits |
| External API unavailable | Explicit error states, cache where available, and graceful degradation |
| Unauthorized conversation access | Authenticated routes, ownership checks, and integration/API tests |

## 13. Success Measures

- Rules-answer factual accuracy on the curated evaluation set.
- Rules reasoning quality.
- Citation existence and relevance.
- Appropriate uncertainty handling.
- Consistent follow-up behavior.
- Low rate of unsupported or invented answers.
- Successful rules refresh and failure-preservation behavior.
- Authentication and conversation privacy coverage.
- Core guest and registered-user flows pass end-to-end tests.
