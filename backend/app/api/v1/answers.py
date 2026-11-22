from fastapi import APIRouter, HTTPException, Request

from app.providers.errors import CardProviderError
from app.schemas.answers import AnswerRequest, AnswerResponse
from app.services.answers import AnswerService, AnswerServiceError


router = APIRouter(prefix="/answers", tags=["answers"])


@router.post("", response_model=AnswerResponse)
async def create_answer(body: AnswerRequest, request: Request) -> AnswerResponse:
    service = AnswerService(
        rules_service=request.app.state.rules_service,
        card_provider=request.app.state.card_provider,
        ai_generation_service=request.app.state.ai_generation_service,
    )
    try:
        return await service.answer(body)
    except AnswerServiceError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from None
    except CardProviderError as error:
        if error.status_code == 429:
            status_code, code, message = (
                503,
                "card_provider_rate_limited",
                "Card evidence is temporarily unavailable",
            )
        elif error.status_code == 504:
            status_code, code, message = (
                504,
                "card_provider_timeout",
                "Card evidence retrieval timed out",
            )
        elif error.status_code == 503:
            status_code, code, message = (
                503,
                "card_provider_unavailable",
                "Card evidence is temporarily unavailable",
            )
        else:
            status_code, code, message = (
                502,
                "card_provider_unavailable",
                "Card evidence is temporarily unavailable",
            )
        raise HTTPException(
            status_code=status_code,
            detail={"code": code, "message": message},
        ) from None
    except Exception:
        # Adapter exceptions are intentionally translated without forwarding raw details.
        raise HTTPException(
            status_code=502,
            detail={
                "code": "answer_evidence_unavailable",
                "message": "Answer evidence is temporarily unavailable",
            },
        ) from None
