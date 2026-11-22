from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.providers.base import CardProvider
from app.schemas.cards import CardDetail, CardSearchRequest, CardSearchResponse


router = APIRouter(prefix="/cards", tags=["cards"])


def get_card_provider(request: Request) -> CardProvider:
    return request.app.state.card_provider


@router.get("", response_model=CardSearchResponse)
async def search_cards(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    provider: CardProvider = Depends(get_card_provider),
) -> CardSearchResponse:
    if not q.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid request")
    search_request = CardSearchRequest(q=q, limit=limit)
    return await provider.search_cards(search_request)


@router.get("/{card_id}", response_model=CardDetail)
async def get_card(
    card_id: str,
    provider: CardProvider = Depends(get_card_provider),
) -> CardDetail:
    return await provider.get_card(card_id)
