import asyncio
import gzip
import json
import re
import tempfile
import zlib
from datetime import datetime
from urllib.parse import quote, urlsplit
from typing import Any, BinaryIO

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
    _max_bulk_metadata_bytes = 1024 * 1024
    _max_bulk_compressed_bytes = 256 * 1024 * 1024
    _max_bulk_uncompressed_bytes = 1024 * 1024 * 1024
    _max_bulk_line_bytes = 1024 * 1024
    _max_bulk_names = 1_000_000
    _bulk_download_timeout_seconds = 180.0

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

    async def get_card_names(self) -> list[str]:
        try:
            with tempfile.TemporaryFile() as metadata, tempfile.TemporaryFile() as archive:
                await asyncio.wait_for(
                    self._download_bulk("/bulk-data/oracle-cards", metadata, self._max_bulk_metadata_bytes),
                    timeout=self._bulk_download_timeout_seconds,
                )
                metadata.seek(0)
                try:
                    data = json.load(metadata)
                except (ValueError, UnicodeDecodeError, RecursionError):
                    raise self._malformed_response() from None
                if not isinstance(data, dict) or data.get("object") != "bulk_data" or data.get("type") != "oracle_cards":
                    raise self._malformed_response()
                size = data.get("compressed_size")
                if type(size) is not int or not 0 < size <= self._max_bulk_compressed_bytes:
                    raise self._malformed_response()
                uri = self._validated_bulk_uri(data.get("jsonl_download_uri"))
                downloaded = await asyncio.wait_for(
                    self._download_bulk(uri, archive, size),
                    timeout=self._bulk_download_timeout_seconds,
                )
                if downloaded != size:
                    raise self._malformed_response()
                archive.seek(0)
                parser = asyncio.create_task(asyncio.to_thread(self._parse_bulk_names, archive))
                try:
                    return await asyncio.shield(parser)
                except asyncio.CancelledError:
                    # Keep the temporary file open until the worker has finished reading it.
                    try:
                        await parser
                    except Exception:
                        pass
                    raise
        except asyncio.TimeoutError:
            raise CardProviderError("provider_timeout", "Card provider timed out", 504) from None
        except OSError:
            raise CardProviderError("provider_unavailable", "Card provider is unavailable", 503) from None

    @classmethod
    def _validated_bulk_uri(cls, uri: Any) -> str:
        if not isinstance(uri, str) or len(uri) > 2048:
            raise cls._malformed_response()
        try:
            parts = urlsplit(uri)
            valid = (
                parts.scheme == "https"
                and parts.netloc.lower() in {"data.scryfall.io", "data.scryfall.io:443"}
                and parts.hostname == "data.scryfall.io"
                and parts.port in (None, 443)
                and not parts.query
                and not parts.fragment
                and re.fullmatch(r"/[A-Za-z0-9._/-]+\.jsonl\.gz", parts.path) is not None
                and all(part not in {"", ".", ".."} for part in parts.path[1:].split("/"))
                and uri == uri.strip()
                and not any(ord(char) < 33 or ord(char) == 127 for char in uri)
                and "?" not in uri
                and "#" not in uri
            )
        except ValueError:
            valid = False
        if not valid:
            raise cls._malformed_response()
        return uri

    async def _download_bulk(self, path: str, target: BinaryIO, limit: int) -> int:
        for attempt in range(self._max_attempts):
            target.seek(0)
            target.truncate()
            try:
                response = await self._request_with_rate_limit("GET", path, stream=True)
                try:
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt + 1 < self._max_attempts:
                            await asyncio.sleep(self._retry_delay_seconds)
                            continue
                        if response.status_code == 429:
                            raise CardProviderError("provider_rate_limited", "Card provider rate limit reached", 429)
                        raise CardProviderError("provider_unavailable", "Card provider is unavailable", 503)
                    if response.status_code != 200:
                        raise CardProviderError("provider_unavailable", "Card provider request failed", 502)
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise self._malformed_response()
                    length = response.headers.get("content-length")
                    if length is not None and (
                        len(length) > 20 or not length.isascii() or not length.isdecimal() or int(length) > limit
                    ):
                        raise self._malformed_response()
                    total = 0
                    async for chunk in response.aiter_raw():
                        total += len(chunk)
                        if total > limit:
                            raise self._malformed_response()
                        target.write(chunk)
                    if length is not None and total != int(length):
                        raise self._malformed_response()
                    return total
                finally:
                    await response.aclose()
            except httpx.TimeoutException:
                if attempt + 1 == self._max_attempts:
                    raise CardProviderError("provider_timeout", "Card provider timed out", 504) from None
            except httpx.RequestError:
                if attempt + 1 == self._max_attempts:
                    raise CardProviderError("provider_unavailable", "Card provider is unavailable", 503) from None
            await asyncio.sleep(self._retry_delay_seconds)
        raise CardProviderError("provider_unavailable", "Card provider is unavailable", 503)

    @classmethod
    def _parse_bulk_names(cls, archive: BinaryIO) -> list[str]:
        names: dict[str, None] = {}
        total = 0
        try:
            with gzip.GzipFile(fileobj=archive, mode="rb") as source:
                while True:
                    line = source.readline(cls._max_bulk_line_bytes + 1)
                    if not line:
                        break
                    total += len(line)
                    if len(line) > cls._max_bulk_line_bytes or total > cls._max_bulk_uncompressed_bytes:
                        raise ValueError("Bulk data too large")
                    card = json.loads(line.decode("utf-8"), parse_constant=cls._invalid_json_constant)
                    if not isinstance(card, dict):
                        raise ValueError("Invalid card")
                    cls._add_bulk_name(names, card.get("name"))
                    if "card_faces" in card:
                        faces = card["card_faces"]
                        if not isinstance(faces, list):
                            raise ValueError("Invalid faces")
                        for face in faces:
                            if not isinstance(face, dict):
                                raise ValueError("Invalid face")
                            cls._add_bulk_name(names, face.get("name"))
            if not names:
                raise ValueError("Empty bulk data")
        except (OSError, EOFError, ValueError, UnicodeDecodeError, RecursionError, zlib.error):
            raise cls._malformed_response() from None
        return list(names)

    @classmethod
    def _add_bulk_name(cls, names: dict[str, None], name: Any) -> None:
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Invalid name")
        names[name] = None
        if len(names) > cls._max_bulk_names:
            raise ValueError("Too many names")

    @staticmethod
    def _invalid_json_constant(value: str) -> None:
        raise ValueError("Invalid JSON constant")

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
            data = await self._request_json("GET", "/catalog/card-types")
            return (
                data.get("object") == "catalog"
                and isinstance(data.get("data"), list)
                and type(data.get("total_values")) is int
            )
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
        stream: bool = False,
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
            if stream:
                request = self._client.build_request(
                    method, path, params=params, headers={"Accept-Encoding": "identity"}
                )
                return await self._client.send(request, stream=True, follow_redirects=False)
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
