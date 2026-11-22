# Scry-X-AI — Product Requirements Document (PRD)

**Product:** Scry-X-AI  
**Release:** MVP 1 — Rules Assistant  
**Document status:** Draft for review  
**Last updated:** 2026-11-22

## 1. Product overview

Scry-X-AI is an unofficial, AI-powered Magic: The Gathering (MTG) rules assistant. It lets players ask natural-language questions about card interactions and game rules, then returns an explanation grounded in retrieved card data, the Magic: The Gathering Comprehensive Rules, and available card-specific rulings.

The product is an assistant for researching and understanding rules. It is not an official ruling from Wizards of the Coast and does not replace an in-person judge or official tournament policy.

### Product vision

Make complex MTG rules interactions easier to understand by combining reliable source retrieval with clear, traceable AI explanations.

### MVP value proposition

A player can ask a question such as:

> What happens if Blood Moon is on the battlefield with Urza's Saga?

The application identifies the relevant cards, retrieves their current card text and relevant rules material, and presents an explanation with references that the player can inspect.

## 2. Problem statement

MTG interactions can be difficult to resolve by reading card text alone. Players may need to understand layers, continuous effects, type-changing effects, triggered abilities, state-based actions, replacement effects, or the interaction between several rules.

Existing card databases and rules documents are valuable references, but finding the exact relevant material and connecting it to a particular game state can take time and rules knowledge.

Players need a convenient way to:
- Describe an interaction in ordinary language.
- Identify the cards involved without knowing their exact names.
- Find relevant official card text and rules.
- Understand how the retrieved rules apply to the described situation.
- Verify the answer using visible references.

## 3. Target users

### Primary users
- Casual and competitive MTG players who understand the basic game but need help with complex interactions.
- Players who want a faster way to locate and understand relevant rules and card rulings.

### Secondary users
- Newer players learning how game mechanics interact.
- Judges and experienced players using the application as a research aid, not as an authoritative ruling engine.

## 4. Goals and success measures

### Product goals
1. Accept natural-language questions about MTG rules and card interactions.
2. Identify relevant cards reliably, including common fuzzy-name matches.
3. Retrieve current card data, card-specific rulings when available, and relevant Comprehensive Rules.
4. Generate explanations grounded in retrieved evidence.
5. Display citations that let users verify the underlying sources.
6. Communicate uncertainty rather than fabricate rules or references.

### MVP success measures
These are proposed release targets and should be confirmed during validation.

| Measure | MVP target |
|---|---:|
| Card identification accuracy on a curated test set | ≥ 95% |
| Correct rule-reference IDs on a curated test set | ≥ 95% |
| Answers with valid, retrievable citations | 100% |
| Evaluation questions with materially correct conclusions | ≥ 85% initially |
| Unsupported claims presented as certain | 0 in release-blocking tests |
| Successful end-to-end responses on supported test cases | ≥ 95% |

The evaluation set should contain at least 30–50 curated questions, including known edge cases. Accuracy targets are release goals, not claims of guaranteed judge-level correctness.

## 5. MVP scope

### In scope

#### 5.1 Rules data
- Ingest a published version of the Magic: The Gathering Comprehensive Rules from an official Wizards of the Coast source.
- Store the rules text in a locally queryable database.
- Record source URL, retrieved timestamp, source/version date where available, and a content checksum.
- Preserve the rules version used to answer each question.
- Check official-source freshness during startup and at least every 24 hours.
- Support controlled, administrator-triggered manual refresh.
- Preserve the last successfully verified rules dataset when an update or verification fails.
- Record publication date, verification date, update status, and active dataset metadata.
- Disclose when rules freshness cannot be confirmed.

#### 5.2 Card data
- Retrieve card details from Scryfall.
- Store or cache the fields required by the application: card name, Oracle ID, set/collector metadata where useful, type line, mana cost, Oracle text, image URI, and relevant identifiers.
- Retrieve card-specific rulings from Scryfall when available.
- Record source and retrieval/update timestamps for cached data.
- Respect Scryfall API usage guidance and rate limits.

#### 5.3 Card identification
- Detect likely card names mentioned in a question.
- Attempt exact and fuzzy matching.
- Return one confident match when appropriate.
- Ask the user to select a card when multiple plausible matches exist or the match is uncertain.
- Do not silently choose an ambiguous card.
- Allow the user to correct or remove an identified card before submitting the question.

#### 5.4 Rules retrieval and answer generation
- Retrieve relevant Comprehensive Rules using a hybrid of structured rule-number lookup and text/keyword search.
- Retrieve Oracle text and available rulings for identified cards.
- Build a bounded context package for the LLM.
- Generate a concise answer that distinguishes source facts from interpretation.
- Include applicable rule numbers and source references.
- Indicate when evidence is insufficient or the described game state is ambiguous.
- Do not invent rule numbers, card rulings, or source quotations.

#### 5.5 User interface
- Next.js and React chat interface built with TypeScript, Tailwind CSS, and shadcn/ui.
- Question input and conversation display.
- Related-card panel showing identified cards and Oracle text.
- Rules and references panel showing retrieved rules, rulings, and source/version metadata.
- Clear loading, error, ambiguity, and insufficient-evidence states.
- Responsive layout suitable for desktop and mobile.
- Support light and dark themes, with dark mode as the default.

#### 5.6 Conversation history and follow-up questions
- Guest users can retain conversation history locally in their browser.
- Guest history must not be uploaded to an account or server automatically.
- Registered users can persist conversation history in PostgreSQL.
- Registered users can access their conversations across devices.
- Follow-up questions reuse relevant recent context while keeping context bounded.
- Users can only access their own registered conversations.

#### 5.7 Administration
- Provide a restricted administrator dashboard.
- Display backend, database, external API, provider, fallback-model, rules-freshness, and model-usage health.
- Support role-based access and administrator-triggered rules refresh.
- Never expose provider keys, secrets, or private configuration values in dashboard responses or browser code.

### Out of scope for MVP 1
- Guaranteed judge-level or tournament-authoritative rulings.
- Full game-state simulation or comprehensive rules engine.
- Rules coverage guarantees for every possible interaction.
- Deck analysis, deck building, or collection management.
- Community voting, comments, or public answer sharing.
- Rules quiz generation or training modes.
- Voice input or image-based card recognition.
- Multi-agent reasoning.
- Fine-tuning a model on MTG rules.
- Vector database/embedding infrastructure unless evaluation demonstrates that basic retrieval is insufficient.
- Zero-downtime rules-data migration.

## 6. User journeys

### Journey A — Supported question with clear card matches
1. User enters a rules question.
2. Backend extracts candidate card names.
3. Card lookup returns confident matches.
4. User sees the identified cards and can correct them if needed.
5. Backend retrieves Oracle text, relevant rulings, and relevant Comprehensive Rules.
6. AI generates an evidence-grounded explanation.
7. UI displays the answer, related cards, rule references, and source metadata.

### Journey B — Ambiguous card match
1. User enters a question containing a partial or ambiguous card name.
2. Lookup finds multiple plausible matches.
3. UI asks the user to choose the intended card.
4. The question is not answered using an unconfirmed ambiguous match.
5. After selection, the normal answer flow continues.

### Journey C — Insufficient evidence
1. User submits a question.
2. Retrieval finds no sufficiently relevant evidence, or the question lacks necessary game-state details.
3. The assistant explains what is missing or uncertain.
4. It asks one focused clarification question when that would materially help.
5. It does not fabricate a definitive ruling.

## 7. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The user can submit a natural-language MTG rules question. | Must |
| FR-02 | The system identifies candidate card names in the question. | Must |
| FR-03 | The system supports exact and fuzzy card lookup. | Must |
| FR-04 | The system detects ambiguous matches and requires user confirmation. | Must |
| FR-05 | The system retrieves card Oracle text and available card-specific rulings. | Must |
| FR-06 | The system stores and searches a versioned Comprehensive Rules dataset. | Must |
| FR-07 | The system retrieves relevant rules for a question. | Must |
| FR-08 | The AI answer is grounded in the retrieved context. | Must |
| FR-09 | The answer displays rule numbers and source references. | Must |
| FR-10 | The UI displays identified cards and relevant source material. | Must |
| FR-11 | The system communicates uncertainty and insufficient evidence. | Must |
| FR-12 | The system records which rules-data version was used for an answer. | Must |
| FR-13 | The system provides useful loading and error states. | Must |
| FR-14 | The system caches external card data and observes API rate limits. | Should |
| FR-15 | The system supports manual rules-data refresh with validation. | Should |
| FR-16 | Guest conversation history remains local to the browser and is not uploaded without consent. | Must |
| FR-17 | Registered users can persist and retrieve their own conversation history across devices. | Must |
| FR-18 | Follow-up questions preserve relevant bounded conversation context. | Must |
| FR-19 | The system verifies rules freshness every 24 hours and on startup when stale. | Must |
| FR-20 | The UI supports light and dark themes, with dark mode as the default. | Must |
| FR-21 | The administrator dashboard exposes operational health and supports authorized rules refresh. | Must |
| FR-22 | The AI provider layer supports configurable models and bounded failover. | Must |
| FR-23 | OpenRouter is the initial provider, with provider-independent configuration and model recording. | Must |
| FR-24 | Free models are the default; paid usage requires explicit enablement and spending controls. | Must |

## 8. Non-functional requirements

### Accuracy and trust
- Retrieved source material must be distinguishable from generated explanation.
- Every displayed rule citation must resolve to a rule present in the active or recorded rules dataset.
- The model must be instructed to use only the supplied evidence for factual rules claims and to state when evidence is insufficient.
- The application must not describe its output as an official ruling.

### Performance
Proposed targets under normal development/staging conditions:
- Card lookup: p95 under 2 seconds when cache is warm.
- Rules retrieval: p95 under 1 second for local database queries.
- End-to-end answer: target p95 under 15 seconds, excluding unusually slow upstream model/API responses.
- Show progress/loading feedback while processing.

### Reliability
- External API failures must produce a recoverable error, not a fabricated answer.
- Data ingestion must validate a new dataset before activating it.
- Preserve the last known-good rules dataset if an update fails.
- Preserve the last known-good rules dataset if official-source verification fails.
- Disclose freshness verification failures and do not present stale unverified data as current.
- Avoid logging API keys or unnecessary personal information.

### Security and privacy
- Store API keys and secrets only in server-side environment variables.
- Never expose the LLM provider key or Scryfall credentials (if any) to the browser.
- Validate request sizes and input types.
- Apply basic rate limiting to public AI endpoints before public launch.
- Do not upload guest history automatically.
- Restrict registered conversation access to its owner.
- Protect authentication routes and administrator operations with appropriate authorization.

### Accessibility and usability
- Responsive layout.
- Keyboard-operable question submission and card selection.
- Clear labels and readable citation links.
- Distinguish errors, ambiguity prompts, and normal answers without relying on color alone.

## 9. Data sources and governance

### Comprehensive Rules
Use the official Wizards of the Coast publication as the authoritative source for the rules text. Record the source URL, publication/version date when available, retrieval timestamp, and checksum.

### Card data and rulings
Use Scryfall as the card-data provider for Oracle text, card identifiers, image references, and published card rulings. Scryfall data is a data source, not the authority for interpreting all game rules.

### Update policy
- Check official-source freshness at backend startup and at least every 24 hours.
- Support administrator-triggered manual verification and refresh.
- Parse and validate the new rules document before activation.
- Store version metadata and retain enough history to identify the dataset used by previous answers.
- If ingestion fails, continue serving the last known-good dataset.
- Clearly label the data version and last successful refresh in the UI or source details.

## 10. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM produces plausible but incorrect rules explanations | High | RAG, constrained prompts, citation validation, curated evaluation set |
| Wrong card selected from fuzzy match | High | Confidence threshold, ambiguity confirmation, user correction |
| Rules data becomes stale | High | Version metadata, checksum, refresh validation, visible last-updated date |
| Retrieval misses the decisive rule | High | Curated tests, rule-number/keyword search, inspect retrieval failures |
| Missing game-state details | Medium | Ask a focused clarification question; avoid assumptions |
| External API unavailable or rate-limited | Medium | Cache, retries with limits, graceful degradation |
| Serverless filesystem is treated as persistent storage | Medium | Package read-only rules data with deployment or use managed persistent storage |
| Scope expands into a full rules engine | High | Keep simulation, deck analysis, and advanced features out of MVP |

## 11. Dependencies and assumptions

- The user has access to an LLM provider/API suitable for question answering.
- The official Comprehensive Rules can be obtained and processed in a permitted format.
- Scryfall API and data usage policies are reviewed and followed.
- The selected Vercel deployment configuration supports the chosen Python/FastAPI runtime and its dependency/runtime constraints.
- Rules and card datasets are read-heavy for MVP.
- A human-curated evaluation set can be assembled and reviewed.

## 12. Release acceptance criteria

MVP 1 is ready for a limited public release when:

1. A user can submit a natural-language rules question through the web UI.
2. The system identifies relevant cards and handles ambiguous matches without silently guessing.
3. Card Oracle text and available rulings are retrieved and displayed.
4. Relevant Comprehensive Rules are retrieved from a versioned dataset.
5. The generated answer explains the interaction and cites the rules it relies on.
6. Every displayed rule citation resolves to the corresponding stored rule.
7. The assistant communicates uncertainty when the evidence is insufficient.
8. The curated evaluation set meets the agreed release thresholds, with no unresolved critical hallucination or citation failures.
9. Secrets are not exposed to the frontend or committed to source control.
10. Automated tests pass and the application is deployed to a test/live environment.
11. README documentation explains setup, data sources, limitations, and deployment.
12. Guest history remains local unless the user explicitly registers or consents to migration.
13. Registered conversation history is protected against cross-user access.
14. Follow-up questions use bounded relevant context.
15. Rules freshness verification and failed-update behavior meet the 24-hour requirements.
16. The administrator dashboard is restricted and does not expose secrets.
17. Light and dark themes pass component and accessibility checks.
18. Provider timeout, rate-limit, and failover behavior pass automated tests.
19. Independent QA reports confirmed defects and test results for the implementation.

## 13. Product disclaimer

Scry-X-AI is an unofficial fan-made rules research assistant and is not affiliated with, endorsed, or sponsored by Wizards of the Coast. Its AI-generated explanations may be incomplete or incorrect. Players should consult the official rules and a qualified judge for authoritative or tournament-sensitive decisions.

## 14. Future Roadmap

After MVP validation:
- Improved semantic retrieval and embeddings.
- More advanced layer/timestamp explanation workflows.
- User feedback and answer-quality reporting.
- Judge-reviewed benchmark dataset.
