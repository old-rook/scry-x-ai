import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.cards import CardSearchRequest
from app.providers.scryfall import ScryfallProvider
from app.rules.service import RulesService


CARD = {
    "id": "card-123",
    "oracle_id": "oracle-123",
    "name": "Lightning Bolt",
    "mana_cost": "{R}",
    "type_line": "Instant",
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    "set_name": "Alpha",
    "rarity": "common",
    "image_uris": {
        "normal": "https://cards.scryfall.io/normal/front/0/0/000.jpg",
        "large": "https://cards.scryfall.io/large/front/0/0/000.jpg",
    },
    "updated_at": "2026-01-02T03:04:05.000Z",
}


def api_client(transport: httpx.AsyncBaseTransport) -> TestClient:
    provider = ScryfallProvider(transport=transport)
    rules_dir = Path(mkdtemp(prefix="scry-x-rules-test-"))
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "status.json").write_text(
        json.dumps(
            {
                "status": "verified",
                "last_verified_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    rules_service = RulesService(
        rules_dir,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, request=request)
        ),
    )
    return TestClient(
        create_app(
            Settings(database_url=None, rules_refresh_mode="external"),
            card_provider=provider,
            rules_service=rules_service,
        )
    )


def test_search_normalizes_cards_and_honors_limit() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cards/search"
        assert request.url.params["q"] == "Lightning Bolt"
        return httpx.Response(
            200,
            json={"total_cards": 2, "data": [CARD, {**CARD, "id": "card-456"}]},
        )

    with api_client(httpx.MockTransport(handle)) as client:
        response = client.get("/api/v1/cards", params={"q": "Lightning Bolt", "limit": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["cards"]) == 1
    assert data["cards"][0]["id"] == "card-123"
    assert data["cards"][0]["mana_cost"] == "{R}"
    assert data["cards"][0]["image_urls"]["normal"] == CARD["image_uris"]["normal"]
    assert data["cards"][0]["source"] == "scryfall"
    assert data["cards"][0]["source_updated_at"] == "2026-01-02T03:04:05Z"


def test_detail_normalizes_rulings_and_source_values() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cards/card-123":
            return httpx.Response(200, json=CARD)
        assert request.url.path == "/cards/card-123/rulings"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "oracle_id": "oracle-123",
                        "published_at": "2020-01-01",
                        "comment": "A Gatherer ruling.",
                        "source": "wotc",
                    },
                    {
                        "oracle_id": "oracle-123",
                        "published_at": "2021-01-01",
                        "comment": "A Scryfall ruling.",
                        "source": "Scryfall",
                    },
                ]
            },
        )

    with api_client(httpx.MockTransport(handle)) as client:
        response = client.get("/api/v1/cards/card-123")

    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == "card-123"
    assert [ruling["source"] for ruling in detail["rulings"]] == ["gatherer", "scryfall"]
    assert detail["rulings"][0]["oracle_card_id"] == "oracle-123"
    assert detail["rulings"][0]["card_name"] == "Lightning Bolt"
    assert detail["rulings"][0]["source_url"] is None


def test_multiface_detail_uses_face_fields_when_top_level_fields_are_absent() -> None:
    multiface = {
        "id": "split-card-123",
        "oracle_id": "split-oracle-123",
        "name": "Fire // Ice",
        "set_name": "Apocalypse",
        "rarity": "uncommon",
        "card_faces": [
            {
                "name": "Fire",
                "mana_cost": "{1}{R}",
                "type_line": "Instant",
                "oracle_text": "Fire deals 2 damage divided as you choose among one or two targets.",
                "image_uris": {
                    "normal": "https://cards.scryfall.io/normal/fire.jpg",
                },
            },
            {
                "name": "Ice",
                "mana_cost": "{1}{U}",
                "type_line": "Instant",
                "oracle_text": "Tap target permanent. Draw a card.",
                "image_uris": {
                    "normal": "https://cards.scryfall.io/normal/ice.jpg",
                },
            },
        ],
    }

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cards/split-card-123":
            return httpx.Response(200, json=multiface)
        assert request.url.path == "/cards/split-card-123/rulings"
        return httpx.Response(200, json={"data": []})

    with api_client(httpx.MockTransport(handle)) as client:
        response = client.get("/api/v1/cards/split-card-123")

    assert response.status_code == 200
    detail = response.json()
    assert detail["name"] == "Fire // Ice"
    assert detail["mana_cost"] == "{1}{R} // {1}{U}"
    assert detail["type_line"] == "Instant // Instant"
    assert detail["oracle_text"] == (
        "Fire deals 2 damage divided as you choose among one or two targets."
        "\n\n---\n\n"
        "Tap target permanent. Draw a card."
    )
    assert detail["image_urls"]["front"] == multiface["card_faces"][0]["image_uris"]["normal"]
    assert detail["image_urls"]["back"] == multiface["card_faces"][1]["image_uris"]["normal"]


def test_multiface_detail_keeps_present_top_level_fields_authoritative() -> None:
    card = ScryfallProvider._normalize_card(
        {
            "id": "split-card-456",
            "name": "Top-level name",
            "mana_cost": "{7}",
            "type_line": "Top-level type",
            "oracle_text": "Top-level rules text",
            "card_faces": [
                {
                    "name": "Front face",
                    "mana_cost": "{R}",
                    "type_line": "Front type",
                    "oracle_text": "Front rules text",
                },
                {
                    "name": "Back face",
                    "mana_cost": "{U}",
                    "type_line": "Back type",
                    "oracle_text": "Back rules text",
                },
            ],
        }
    )

    assert card.name == "Top-level name"
    assert card.mana_cost == "{7}"
    assert card.type_line == "Top-level type"
    assert card.oracle_text == "Top-level rules text"


def test_search_empty_result_is_normalized_from_scryfall_not_found() -> None:
    with api_client(
        httpx.MockTransport(
            lambda _: httpx.Response(404, json={"details": "private upstream response"})
        )
    ) as client:
        response = client.get("/api/v1/cards", params={"q": "no matching card"})

    assert response.status_code == 200
    assert response.json() == {"cards": [], "total": 0}


def test_malformed_upstream_payload_returns_safe_error() -> None:
    with api_client(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"total_cards": 1, "data": [{"details": "secret upstream body"}]},
            )
        )
    ) as client:
        response = client.get("/api/v1/cards", params={"q": "Bolt"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "malformed_provider_response",
            "message": "Card provider returned an invalid response",
        }
    }
    assert "secret upstream body" not in response.text


def test_rate_limit_retries_once_and_does_not_expose_upstream_body() -> None:
    calls = 0
    request_times: list[float] = []

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        request_times.append(time.monotonic())
        return httpx.Response(429, text="private rate limit response")

    with api_client(httpx.MockTransport(handle)) as client:
        response = client.get("/api/v1/cards", params={"q": "Bolt"})

    assert calls == 2
    assert request_times[1] - request_times[0] >= 0.5
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "provider_rate_limited"
    assert "private rate limit response" not in response.text


def test_timeout_retries_once_and_returns_explicit_error() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("private timeout details", request=request)

    with api_client(httpx.MockTransport(handle)) as client:
        response = client.get("/api/v1/cards", params={"q": "Bolt"})

    assert calls == 2
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "provider_timeout"
    assert "private timeout details" not in response.text


def test_network_failure_retries_once_and_returns_explicit_error() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("private connection details", request=request)

    with api_client(httpx.MockTransport(handle)) as client:
        response = client.get("/api/v1/cards", params={"q": "Bolt"})

    assert calls == 2
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_unavailable"
    assert "private connection details" not in response.text


def test_health_reports_provider_unavailable() -> None:
    with api_client(
        httpx.MockTransport(lambda _: httpx.Response(503, text="private upstream body"))
    ) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["scryfall"] == {"status": "unavailable"}


def test_concurrent_search_requests_obey_search_rate_limit() -> None:
    request_times: list[float] = []

    def handle(_: httpx.Request) -> httpx.Response:
        request_times.append(time.monotonic())
        return httpx.Response(200, json={"total_cards": 0, "data": []})

    async def request_twice() -> None:
        provider = ScryfallProvider(transport=httpx.MockTransport(handle))
        try:
            request = CardSearchRequest(q="Bolt")
            await asyncio.gather(provider.search_cards(request), provider.search_cards(request))
        finally:
            await provider.close()

    asyncio.run(request_twice())
    assert len(request_times) == 2
    assert request_times[1] - request_times[0] >= 0.5


def test_concurrent_standard_requests_obey_rate_limit() -> None:
    request_times: list[float] = []

    def handle(_: httpx.Request) -> httpx.Response:
        request_times.append(time.monotonic())
        return httpx.Response(200, json={"object": "catalog"})

    async def request_twice() -> None:
        provider = ScryfallProvider(transport=httpx.MockTransport(handle))
        try:
            await asyncio.gather(provider.health_check(), provider.health_check())
        finally:
            await provider.close()

    asyncio.run(request_twice())
    assert len(request_times) == 2
    assert request_times[1] - request_times[0] >= 0.1
