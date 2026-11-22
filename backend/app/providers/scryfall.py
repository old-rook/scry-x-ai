import asyncio
from datetime import datetime
from urllib.parse import quote
from typing import Any

import httpx
from pydantic import ValidationError

from app.providers.errors import CardProviderError
from app.schemas.cards import CardDetail, CardRuling, CardSearchRequest, CardSearchResponse


ORACLE_TEXT_FACE_SEPARATOR = "\n\n---\n\n"


class ScryfallProvider:
    """HTTP adapter that translates Scryfall data into the application card contracts."""

    base_url = "https://api.scryfall.com"
    _max_attempts = 2
    _retry_delay_seconds = 0.1

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            headers={"User-Agent": "Scry-X-AI/0.1.0", "Accept": "application/json"},
        )
        self._request_lock = asyncio.Lock()
        self._last_request_at: dict[str, float] = {}

    async def search_cards(self, request: CardSearchRequest) -> CardSearchResponse:
        try:
            data = await self._request_json(
                "GET",
                "/cards/search",
                params={"q": request.q, "unique": "cards"},
            )
        except CardProviderError as error:
            if error.code == "card_not_found":
                return CardSearchResponse(cards=[], total=0)
            if error.code == "invalid_query":
                raise
            raise

        try:
            total = data.get("total_cards")
            cards = data.get("data")
            if type(total) is not int or total < 0 or not isinstance(cards, list):
                raise ValueError("Invalid search response")
            normalized = [self._normalize_card(card) for card in cards[: request.limit]]
            return CardSearchResponse(cards=normalized, total=total)
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise self._malformed_response() from None

    async def get_card(self, card_id: str) -> CardDetail:
        encoded_id = quote(card_id, safe="")
        card_data = await self._request_json("GET", f"/cards/{encoded_id}")
        rulings_data = await self._request_json("GET", f"/cards/{encoded_id}/rulings")
        try:
            card = self._normalize_card(card_data)
            ruling_rows = rulings_data.get("data")
            if not isinstance(ruling_rows, list):
                raise ValueError("Invalid rulings response")
            card.rulings = [self._normalize_ruling(row, card_data) for row in ruling_rows]
            return card
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise self._malformed_response() from None

    async def health_check(self) -> bool:
        try:
            data = await self._request_json("GET", "/")
            return isinstance(data, dict) and data.get("object") == "catalog"
        except CardProviderError:
            return False

    async def close(self) -> None:
        await self._client.aclose()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            try:
                response = await self._request_with_rate_limit(method, path, params=params)
            except httpx.TimeoutException:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(self._retry_delay_seconds)
                    continue
                raise CardProviderError(
                    "provider_timeout",
                    "Card provider timed out",
                    504,
                ) from None
            except httpx.RequestError:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(self._retry_delay_seconds)
                    continue
                raise CardProviderError(
                    "provider_unavailable",
                    "Card provider is unavailable",
                    503,
                ) from None

            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(self._retry_delay_seconds)
                    continue
                if response.status_code == 429:
                    raise CardProviderError(
                        "provider_rate_limited",
                        "Card provider rate limit reached",
                        429,
                    )
                raise CardProviderError(
                    "provider_unavailable",
                    "Card provider is unavailable",
                    503,
                )
            if response.status_code == 404:
                raise CardProviderError("card_not_found", "Card was not found", 404)
            if response.status_code == 400:
                raise CardProviderError("invalid_query", "Card search query is invalid", 422)
            if response.is_error:
                raise CardProviderError(
                    "provider_unavailable",
                    "Card provider request failed",
                    502,
                )

            try:
                payload = response.json()
            except (ValueError, UnicodeDecodeError):
                raise self._malformed_response() from None
            if not isinstance(payload, dict):
                raise self._malformed_response()
            return payload

        raise CardProviderError("provider_unavailable", "Card provider is unavailable", 503)

    async def _request_with_rate_limit(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        is_search = method == "GET" and path == "/cards/search"
        loop = asyncio.get_running_loop()
        async with self._request_lock:
            now = loop.time()
            next_allowed_at = self._last_request_at.get("any", now) + 0.1
            if is_search:
                next_allowed_at = max(
                    next_allowed_at,
                    self._last_request_at.get("search", now) + 0.5,
                )
            if now < next_allowed_at:
                await asyncio.sleep(next_allowed_at - now)
            started_at = loop.time()
            self._last_request_at["any"] = started_at
            if is_search:
                self._last_request_at["search"] = started_at
            return await self._client.request(method, path, params=params)

    @classmethod
    def _normalize_card(cls, data: Any) -> CardDetail:
        if not isinstance(data, dict):
            raise ValueError("Invalid card")
        image_urls: dict[str, str] = {}
        top_level_images = data.get("image_uris")
        if isinstance(top_level_images, dict):
            image_urls.update(
                {
                    key: value
                    for key, value in top_level_images.items()
                    if key in {"small", "normal", "large", "png", "art_crop", "border_crop"}
                    and isinstance(value, str)
                }
            )
        card_faces = data.get("card_faces")
        if isinstance(card_faces, list):
            for index, face in enumerate(card_faces):
                if isinstance(face, dict) and isinstance(face.get("image_uris"), dict):
                    image = face["image_uris"].get("normal")
                    if isinstance(image, str):
                        image_urls["front" if index == 0 else "back"] = image

        return CardDetail(
            id=data.get("id"),
            name=cls._card_field(data, card_faces, "name", " // "),
            scryfall_uri=data.get("scryfall_uri"),
            mana_cost=cls._card_field(data, card_faces, "mana_cost", " // "),
            type_line=cls._card_field(data, card_faces, "type_line", " // "),
            oracle_text=cls._card_field(
                data,
                card_faces,
                "oracle_text",
                ORACLE_TEXT_FACE_SEPARATOR,
            ),
            set_name=data.get("set_name"),
            rarity=data.get("rarity"),
            image_urls=image_urls,
            source_updated_at=cls._parse_updated_at(data.get("updated_at")),
        )

    @staticmethod
    def _card_field(
        card_data: dict[str, Any],
        card_faces: Any,
        field_name: str,
        face_separator: str,
    ) -> Any:
        top_level_value = card_data.get(field_name)
        if top_level_value is not None:
            return top_level_value
        if not isinstance(card_faces, list):
            return None
        face_values = [
            value.strip()
            for face in card_faces
            if isinstance(face, dict)
            and isinstance(value := face.get(field_name), str)
            and value.strip()
        ]
        return face_separator.join(face_values) if face_values else None

    @staticmethod
    def _normalize_ruling(data: Any, card_data: dict[str, Any]) -> CardRuling:
        if not isinstance(data, dict):
            raise ValueError("Invalid ruling")
        source = data.get("source")
        if not isinstance(source, str):
            raise ValueError("Invalid ruling source")
        normalized_source = source.strip().casefold()
        if normalized_source == "scryfall":
            source_value = "scryfall"
        elif normalized_source in {"wotc", "gatherer", "wizards of the coast"}:
            source_value = "gatherer"
        else:
            raise ValueError("Unknown ruling source")
        return CardRuling(
            oracle_card_id=data.get("oracle_id") or card_data.get("oracle_id"),
            card_name=card_data.get("name"),
            published_at=data.get("published_at"),
            comment=data.get("comment"),
            source=source_value,
        )

    @staticmethod
    def _parse_updated_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError("Invalid source update timestamp")

    @staticmethod
    def _malformed_response() -> CardProviderError:
        return CardProviderError(
            "malformed_provider_response",
            "Card provider returned an invalid response",
            502,
        )
