import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.schemas import (
    HealthResponse, IdentifyRequest, IdentifyResponse, JudgeRequest,
    JudgeResponse, RulesVersion,
)
from .core.config import get_settings
from .services.card_lookup import CardLookup
from .services.judge_ai import MockLLMClient
from .services.response_validator import validate_answer
from .services.rules_repository import RulesRepository
from .services.scryfall_client import ScryfallClient


settings = get_settings()
settings.validate_required()
rules = RulesRepository(settings.database_path)
rules.initialize()
scryfall = ScryfallClient(settings.scryfall_user_agent)
card_lookup = CardLookup(scryfall)
llm = MockLLMClient()

app = FastAPI(title="Scry-X-AI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    try:
        return await call_next(request)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Unhandled API exception: {exc!r}")
        correlation_id = uuid.uuid4().hex
        return JSONResponse(
            status_code=500,
            content={"detail": "Unexpected internal error", "correlation_id": correlation_id},
        )


@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.get("/api/v1/rules/version", response_model=RulesVersion)
async def rules_version():
    rules.ensure_sample_version()
    version = rules.active_version()
    if not version:
        raise HTTPException(status_code=503, detail="Rules dataset unavailable")
    return {
        "version_id": version["version_id"],
        "source_version_date": version["source_version_date"],
        "fetched_at": version["fetched_at"],
        "source_url": version["source_url"],
    }


@app.post("/api/v1/cards/identify", response_model=IdentifyResponse)
async def identify(request: IdentifyRequest):
    try:
        return await card_lookup.identify(request.question)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Card lookup unavailable") from exc


@app.post("/api/v1/judge/ask", response_model=JudgeResponse)
async def judge(request: JudgeRequest):
    if request.confirmed_cards:
        cards = await card_lookup.resolve_confirmed(
            [card.scryfall_id for card in request.confirmed_cards]
        )
    else:
        identification = await card_lookup.identify(request.question)
        if identification["status"] == "needs_selection":
            version = rules.ensure_sample_version()
            return {
                "status": "needs_selection",
                "summary": "A card match needs your confirmation.",
                "explanation": [],
                "cards": [],
                "ambiguous": identification["ambiguous"],
                "citations": [],
                "rules_version": {
                    "version_id": version["version_id"],
                    "source_version_date": version["source_version_date"],
                    "source_url": version["source_url"],
                },
                "assumptions": [],
                "uncertainties": ["The intended card could not be determined safely."],
                "clarifying_question": "Which card did you mean?",
            }
        cards = identification["cards"]

    retrieved = rules.retrieve(request.question)
    context = {
        "question": request.question,
        "cards": cards,
        "rulings": [],
        "rules": [
            {
                "evidence_id": rule.evidence_id,
                "rule_id": rule.rule_id,
                "text": rule.text,
                "section": rule.section,
                "source_url": rule.source_url,
            }
            for rule in retrieved
        ],
    }
    raw_answer = await llm.generate_judge_answer(question=request.question, context=context)
    try:
        answer = validate_answer(raw_answer, context)
    except ValueError:
        raw_answer = {
            "status": "insufficient_evidence",
            "summary": "The answer could not be safely supported by retrieved evidence.",
            "explanation": [],
            "assumptions": [],
            "citations": [],
            "uncertainties": ["Citation validation failed."],
            "clarifying_question": None,
        }
        answer = validate_answer(raw_answer, context)

    version = rules.ensure_sample_version()
    enriched_citations = []
    for citation in answer.citations:
        rule = next((item for item in context["rules"] if item["evidence_id"] == citation.evidence_id), None)
        if rule:
            enriched_citations.append({
                "evidence_id": citation.evidence_id,
                "kind": "comprehensive_rule",
                "reason": citation.reason,
                "label": f"Comprehensive Rules {rule['rule_id']}",
                "text": rule["text"],
                "source_url": rule["source_url"],
            })

    return {
        "status": answer.status,
        "summary": answer.summary,
        "explanation": answer.explanation,
        "cards": cards,
        "citations": enriched_citations,
        "rules_version": {
            "version_id": version["version_id"],
            "source_version_date": version["source_version_date"],
            "source_url": version["source_url"],
        },
        "assumptions": answer.assumptions,
        "uncertainties": answer.uncertainties,
        "clarifying_question": answer.clarifying_question,
    }
