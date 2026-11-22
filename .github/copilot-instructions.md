# Scry-X-AI — GitHub Copilot Project Instructions

## 1. Project Overview

You are working on **Scry-X-AI**, an unofficial AI-powered Magic: The Gathering rules and card interaction assistant.

The application helps MTG players understand card rules, card interactions, and complicated game situations through accurate explanations supported by authoritative sources.

This is an unofficial application and is not affiliated with or endorsed by Wizards of the Coast.

### Product vision

Build a trusted MTG rules reference where players can:

- Ask complicated card interaction questions.
- Receive accurate, judge-level explanations.
- Look up cards and their Oracle text.
- Understand relevant Comprehensive Rules.
- Access card-specific rulings.
- Follow citations to the sources supporting an answer.

The product should be useful to beginners, experienced players, and judges.

Explain complicated interactions at an appropriate level without sacrificing rules accuracy.

## 2. Core MVP Features

Implement the following features:

1. **Rules Q&A**
   - Natural-language questions about MTG rules.
   - Direct answers followed by relevant explanations.
   - Support complicated rules scenarios.

2. **Card lookup**
   - Search cards by name.
   - Display card details and Oracle text.
   - Retrieve card information through Scryfall.

3. **Card interaction analysis**
   - Analyze interactions involving multiple cards.
   - Identify relevant rules and card-specific rulings.
   - Explain important edge cases.

4. **Rules citations**
   - Cite relevant Comprehensive Rules sections.
   - Cite relevant card-specific rulings.
   - Never fabricate citations.

5. **Gatherer/Scryfall rulings**
   - Retrieve relevant card rulings.
   - Clearly distinguish Oracle text, official rulings, and AI interpretation.

6. **Conversation history**
   - Support conversation history for guests and registered users.

7. **Follow-up questions**
   - Allow users to continue a rules discussion while preserving relevant context.

### Explicitly outside the initial MVP

- Deck analysis.
- Unapproved external integrations.
- Unapproved premium services.
- Features that significantly expand the product scope without approval.

## 3. Technology Stack

Use the following architecture unless an approved technical decision changes it.

### Frontend

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

### Backend

- Python
- FastAPI
- PostgreSQL

### External data

- Scryfall API for card information and card rulings.
- Official Wizards of the Coast sources for Comprehensive Rules verification.

### Deployment

- Frontend should be compatible with Vercel.
- Backend must remain independently deployable to another Python hosting provider.
- Avoid unnecessary vendor lock-in.
- Keep infrastructure and provider configuration environment-driven.

### Engineering requirements

- Maintain clear frontend/backend separation.
- Keep business logic out of UI components.
- Use typed interfaces and validated API contracts.
- Keep database access separate from route handlers.
- Use environment variables for secrets and environment-specific settings.
- Never commit API keys, credentials, or private configuration.
- Do not introduce dependencies or services without approval.

Do not assume the stack or project structure has already been implemented. Inspect the existing repository before making architectural or structural changes.

## 4. AI Provider and Model Management

The application must use a provider-independent AI integration layer.

### Requirements

- OpenRouter is the initial provider.
- Support configurable models and providers.
- Keep provider-specific code isolated behind a common interface.
- Allow configurable primary and fallback models.
- Preserve retrieved context when switching models.
- Support automatic failover for eligible timeouts, rate limits, and provider errors.
- Use bounded retries and exponential backoff.
- Classify and log provider errors.
- Record which model generated an answer.
- Never hardcode model identifiers throughout application code.

Gemini may be supported as an alternative provider.

### Cost policy

Free models are the default.

Paid models and services must be disabled unless explicitly enabled through configuration.

Never silently make a paid request.

If paid usage is enabled, support configurable spending limits and usage monitoring.

Do not assume that a free model, free quota, or provider availability will remain unchanged indefinitely.

### Important distinction

The model used by GitHub Copilot to develop this application is separate from the AI provider and model used by the deployed Scry-X-AI application.

Do not confuse Copilot's coding configuration with the application's runtime AI configuration.

## 5. MTG Knowledge Sources and Retrieval

Use the following sources:

1. Official Magic: The Gathering Comprehensive Rules.
2. Scryfall API.
3. Wizards of the Coast Gatherer.

### Source authority

- The Comprehensive Rules are the primary authority for general game rules.
- Oracle text is the authoritative current text of a card.
- Card-specific rulings provide additional interpretation and clarification.
- Scryfall is a retrieval provider, not a replacement for the official rules.

Do not treat third-party explanations, community discussions, or unofficial websites as authoritative sources.

### Retrieval strategy

Use a hybrid retrieval approach:

1. Store a verified copy of the Comprehensive Rules locally.
2. Retrieve current card information through Scryfall.
3. Retrieve relevant card-specific rulings through Scryfall and/or Gatherer.
4. Identify relevant Comprehensive Rules sections.
5. Combine retrieved information into the context supplied to the AI model.
6. Generate an answer grounded in that context.

Avoid sending the entire Comprehensive Rules document to the model when targeted retrieval is sufficient.

### Ruleset freshness

Always verify whether the locally stored Comprehensive Rules document is current.

Required behavior:

- Check the official source every 24 hours.
- Check freshness during backend startup when the last successful verification is more than 24 hours old.
- Support administrator-triggered manual refresh.
- Validate a downloaded rules document before activating it.
- Preserve the previous valid version if an update fails.
- Record the document version, publication date, verification date, and update status.
- Never claim that the local ruleset is current when verification has failed.

Distinguish between:

- The latest successfully verified local ruleset.
- The latest known available official ruleset.

If freshness cannot be confirmed, disclose that limitation.

## 6. AI Answer Generation and Accuracy

Use this response structure:

1. **Verdict:** Answer the question directly.
2. **Explanation:** Explain why the interaction works that way.
3. **Comprehensive Rules:** Cite relevant rules.
4. **Card rulings:** Include relevant card-specific rulings when applicable.
5. **Additional considerations:** Explain important edge cases when needed.

Adapt the explanation to the complexity of the question and the user's apparent knowledge.

### Accuracy requirements

- Be definitive when authoritative evidence supports a clear conclusion.
- Qualify answers when evidence is incomplete.
- Identify conflicting information instead of hiding it.
- Ask for clarification when required card names, game states, or other information is missing.
- Never invent rules, Oracle text, rulings, or citations.
- Distinguish retrieved facts from AI interpretation.
- Do not present guesses as official rulings.

Rules accuracy is more important than producing a confident-sounding answer.

## 7. User Experience and Design

Build a purpose-built MTG rules platform, not a generic chatbot wrapper.

Use modern web applications such as okizeme.gg as a reference for information density, navigation, and purpose-built interface design.

### Design principles

- Data-first layouts.
- Compact but readable information presentation.
- Useful information visible at a glance.
- Searchable card and rules references.
- Structured card and rules panels.
- Clear citation presentation.
- Responsive layouts.
- Consistent spacing and typography.
- Distinctive MTG-inspired visual language.

Avoid:

- Generic AI chatbot appearance.
- Excessive gradients and glow effects.
- Oversized rounded cards.
- Excessive empty whitespace.
- Decorative animations that do not improve usability.
- Overly elaborate fantasy-game dashboards.

### Theme

Support both light and dark themes.

Dark mode is the default.

## 8. Authentication and Persistence

Use a hybrid guest and registered-user experience.

### Guest users

- Can use rules Q&A and card lookup without registration.
- Conversation history remains local to the browser.
- Do not automatically upload guest conversations to an account without consent.

### Registered users

- Conversation history is persisted in PostgreSQL.
- Users can access their conversations across devices.
- Enforce proper authentication and authorization.
- Users must only access their own conversations.

Protect conversation data and avoid unnecessary collection of personal information.

## 9. Administrator Dashboard

The MVP includes a restricted administrator dashboard.

Required capabilities:

- Backend health status.
- Database health status.
- External API health status.
- Active AI provider and model configuration.
- Fallback provider/model status.
- AI timeouts, rate limits, and failures.
- Model usage monitoring.
- Comprehensive Rules version and verification status.
- Manual ruleset refresh.
- Basic operational settings.

Use role-based access control.

Never expose API keys, secrets, or private configuration values to the frontend.

Do not build a full analytics or moderation platform unless separately approved.

## 10. Testing and Quality Assurance

Testing is part of implementation, not an optional final step.

### Required testing layers

- Unit tests.
- Integration tests.
- Backend API tests.
- Frontend component tests.
- End-to-end tests.
- AI answer evaluation using curated MTG rules questions.

### MTG-specific evaluation

Evaluate answers separately for:

1. Factual accuracy.
2. Rules reasoning.
3. Citation existence.
4. Citation relevance.
5. Uncertainty handling.
6. Consistency.

### Regression testing

Maintain regression tests for verified card interactions and important rules scenarios.

### Additional test coverage

Test:

- Ruleset updates and failed updates.
- Model timeouts and provider failover.
- API failures and rate limits.
- Authentication and authorization.
- Guest and registered-user history.
- Security-sensitive operations.
- Important performance paths.

### Independent QA

The QA Engineer must independently verify implementation.

The QA Engineer must not modify application files.

QA output must include:

- PASS or FAIL.
- Confirmed defects.
- Potential risks.
- Relevant test results.
- Actionable findings.

Do not report a test as passing unless it was actually executed successfully.

## 11. Multi-Agent Development Team

Use GitHub Copilot's native custom agents and subagent delegation within VS Code.

The main Copilot agent is the **Project Coordinator**.

It is responsible for:

- Understanding the user's request.
- Inspecting the relevant project context.
- Planning and coordinating work.
- Delegating specialist tasks.
- Reviewing specialist findings.
- Ensuring user approval requirements are respected.
- Reporting the final result.

### Specialist roles

#### Architect

Responsible for:

- Requirements analysis.
- Technical design.
- Architecture decisions.
- Component boundaries.
- Data flow.
- API contracts.
- Technical risks.
- Story breakdown.

The Architect should normally investigate and propose changes, not independently implement application features.

#### Developer

Responsible for:

- Implementing approved designs.
- Writing maintainable application code.
- Adding and updating tests.
- Fixing defects.
- Running relevant validation.
- Updating relevant documentation.

#### QA Engineer

Responsible for:

- Independently inspecting changed files.
- Verifying requirements against implementation.
- Identifying functional defects.
- Identifying regression risks.
- Running relevant tests.

The QA Engineer must not modify application files.

QA must report only actionable findings and distinguish confirmed bugs from potential risks.

#### Code Reviewer

Responsible for:

- Reviewing implementation quality.
- Identifying maintainability problems.
- Checking security concerns.
- Identifying unnecessary complexity.
- Reviewing error handling and test coverage.
- Checking adherence to project architecture.

The Code Reviewer must not modify application files.

### Delegation rules

- Use only the specialist agents relevant to the task.
- Do not invoke every agent for trivial changes.
- Delegate bounded tasks with explicit objectives and expected outputs.
- Provide only the context and files needed for each task.
- Review subagent findings before acting on them.
- Do not assume that an agent has completed work unless its result is returned and inspected.
- Avoid duplicate investigations.
- Do not delegate dependent implementation tasks in parallel.
- Independent research or review tasks may run in parallel when useful.

The main agent remains responsible for coordinating the workflow and reporting the result.

## 12. Human Approval and Autonomy

The user retains final authority over consequential project decisions.

### Approval is required before

- Installing, uninstalling, or upgrading dependencies.
- Deleting files, folders, features, or data.
- Making major architectural decisions.
- Adding external services or infrastructure.
- Making database schema changes or migrations.
- Changing authentication or security architecture.
- Enabling paid models or services.
- Making significant scope changes.
- Pushing changes to a remote repository.
- Rewriting shared Git history.

Do not interpret an existing approval for one change as permission for unrelated changes.

### Routine work may proceed autonomously

- Reading and inspecting files.
- Implementing approved requirements.
- Writing and updating tests.
- Running tests, linting, and formatting.
- Fixing ordinary bugs.
- Behavior-preserving refactoring.
- Updating relevant documentation.
- Producing implementation plans and reports.

### Approval request format

Before a consequential action, provide:

1. Proposed change.
2. Reason for the change.
3. Files or systems affected.
4. Risks and consequences.
5. Alternatives, when relevant.

Then stop and wait for explicit user approval.

Do not let an agent approve its own consequential decisions.

Tool permissions and approval prompts should be used where available. Written instructions alone are not a security boundary.

## 13. Development Workflow

Use a structured workflow for significant features and a lightweight workflow for small fixes.

### Standard workflow

**Step 1 — Requirements analysis**

- Understand the requested behavior.
- Identify ambiguities.
- Identify constraints and dependencies.
- Ask only necessary clarification questions.

**Step 2 — Planning**

Define:

- Scope.
- Objectives.
- Constraints.
- Expected behavior.
- Acceptance criteria.

**Step 3 — Technical design**

Define:

- Components involved.
- Architecture changes.
- Interfaces and contracts.
- Data flow.
- Dependencies.
- Risks.
- Testing strategy.

Use the Architect agent when the task warrants it.

**Step 4 — Story breakdown**

Break the approved design into small, independently implementable stories.

Each story must contain:

- Story ID.
- Objective.
- Scope.
- Relevant files or components.
- Dependencies.
- Acceptance criteria.
- Testing requirements.
- Rollback considerations.

Stories should be logically isolated, independently testable, and reasonably reversible.

**Step 5 — Incremental implementation**

- Implement one story at a time.
- Follow the approved design.
- Keep changes focused.
- Add tests alongside implementation.
- Avoid unrelated refactoring.
- Do not proceed with dependent work if the current story fails QA.

**Step 6 — Independent QA**

Delegate verification to the QA Engineer.

Review the result and resolve confirmed defects before continuing.

**Step 7 — Code review**

Use the Code Reviewer for significant changes.

Resolve actionable findings or explain why a finding does not apply.

**Step 8 — Completion report**

Summarize:

- What was implemented.
- Files or components changed.
- Tests executed and their results.
- QA result.
- Known limitations.
- Decisions requiring user approval.

### Lightweight workflow

For small bug fixes or minor changes:

1. Inspect relevant files.
2. Identify the cause.
3. Make the smallest safe change.
4. Run focused tests.
5. Report the result.

Do not force the full planning process onto trivial work.

## 14. Token and Credit Optimization

Use context and agent delegation efficiently.

### Repository inspection

- Start by inspecting the project structure and relevant entry points.
- Read only files necessary for the current task.
- Follow imports and dependencies when additional context is required.
- Do not read the entire repository by default.
- Do not repeatedly read unchanged files.
- Inspect existing implementations before creating replacements.
- Reuse existing utilities and patterns when appropriate.

### Agent usage

- Delegate only when the task benefits from specialist context or independent verification.
- Do not spawn agents for trivial edits.
- Give agents focused tasks and relevant file paths.
- Avoid duplicate research and overlapping assignments.
- Do not ask multiple agents to independently inspect the entire repository.
- Prefer one focused QA pass over repeated redundant reviews.

### Testing

- Run focused tests first.
- Run broader regression tests before completing significant changes.
- Avoid repeatedly running the entire test suite when a focused test is sufficient.
- Never skip necessary validation merely to save credits.

### Context management

- Keep implementation context focused on the current story.
- Load only relevant documentation.
- Reuse established decisions rather than rediscovering them.
- Avoid repeating large summaries when a concise reference is sufficient.

Efficiency must not come at the expense of correctness.

## 15. Documentation Organization

Use modular documentation with progressive disclosure.

The project-wide Copilot instructions should remain the entry point.

Suggested documentation:

- `docs/product/PRD.md` — product requirements and scope.
- `docs/architecture/architecture.md` — system architecture and major design decisions.
- `docs/specifications/technical-spec.md` — technical specifications and contracts.
- `docs/workflow/development-workflow.md` — detailed development process.
- `docs/stories/` — implementation stories.
- `docs/decisions/` — architecture decision records.

Adapt this structure to the existing repository. Do not create duplicate or unnecessary folders.

### Documentation rules

- Load only the documents relevant to the current task.
- Keep the current story and its dependencies in context during implementation.
- Update documentation when implementation changes invalidate it.
- Do not duplicate the entire project specification in every agent file.
- Keep shared project rules in this file and specialist-specific instructions in agent files.

## 16. Git and Change Management

- Inspect Git status before making changes.
- Never overwrite or discard existing user changes.
- Do not reset, clean, or rewrite history without approval.
- Keep changes logically isolated.
- Prefer small commits associated with completed stories when appropriate.
- Do not push to remote without approval.
- Never commit secrets, credentials, or local environment files.

Before finalizing, identify which files were changed and whether unrelated changes remain.

## 17. Development Roadmap

Build incrementally in four phases.

### Phase 1 — Foundation

- Project structure.
- Frontend/backend setup.
- Database setup.
- Authentication foundation.
- Scryfall integration.
- Comprehensive Rules ingestion and version management.
- AI provider abstraction.
- Model failover and configuration.

### Phase 2 — Core Rules Assistant

- Natural-language rules Q&A.
- Multi-card interaction analysis.
- Rules retrieval.
- Citation generation.
- Uncertainty handling.
- Follow-up questions.

Prioritize getting a thin, end-to-end working Rules Assistant early.

### Phase 3 — User Experience

- Card lookup interface.
- Conversation history.
- Guest and registered-user experiences.
- Responsive layouts.
- Light and dark themes.
- Purpose-built MTG components.

### Phase 4 — Administration and Quality

- Administrator dashboard.
- AI evaluation framework.
- Citation validation.
- Rules regression testing.
- Security testing.
- Performance testing.
- Deployment and production readiness.

Do not attempt to build every feature at once.

Deliver working increments and request approval before significant scope changes.

## 18. General Engineering Standards

- Prefer simple, maintainable solutions.
- Follow established project conventions.
- Avoid unnecessary abstractions.
- Keep functions and components focused.
- Handle errors explicitly.
- Validate external input.
- Use type hints and TypeScript types appropriately.
- Keep secrets out of source control.
- Avoid unnecessary dependencies.
- Write tests for meaningful behavior changes.
- Keep API contracts consistent.
- Consider security, performance, and accessibility.
- Do not silently change established behavior.

When uncertain about an existing implementation, inspect it before making assumptions.

## 19. Definition of Done

A feature or story is complete when:

- Approved requirements are implemented.
- Acceptance criteria are satisfied.
- Relevant tests have been added or updated.
- Focused tests pass.
- Necessary regression tests pass.
- QA has independently verified significant changes.
- Code review findings are resolved or documented.
- Relevant documentation is updated.
- No unapproved dependencies or architectural changes were introduced.
- No secrets or unintended files were committed.
- The user receives a concise completion report.

Do not claim completion when required validation has not been performed.

## 20. Final Operating Principle

Build Scry-X-AI as a reliable, maintainable, source-grounded MTG rules assistant.

Prioritize rules accuracy, trustworthy citations, clear explanations, and a useful user experience.

Use GitHub Copilot's native VS Code agent capabilities to coordinate specialist agents efficiently.

Work autonomously within approved requirements, but always leave consequential decisions and sensitive project changes under the user's control.