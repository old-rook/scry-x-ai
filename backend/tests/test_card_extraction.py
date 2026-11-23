import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.providers.errors import CardProviderError
from app.services.card_extraction import CardCatalog, NameMatcher


class CatalogProvider:
    def __init__(self, names: list[str] | None = None) -> None:
        self.names = names
        self.calls = 0

    async def get_card_names(self) -> list[str]:
        self.calls += 1
        if self.names is None:
            raise CardProviderError("provider_unavailable", "Unavailable", 503)
        return self.names


def test_phrase_matching_is_case_insensitive_and_prefers_longer_names() -> None:
    matcher = NameMatcher(("Bolt", "Lightning Bolt"))
    assert matcher.match(
        "Can lightning bolt target a bolt? Lightning Bolts don't count."
    ) == ["Lightning Bolt", "Bolt"]


def test_phrase_matching_handles_suffixes_and_word_boundaries() -> None:
    matcher = NameMatcher(("Ring", "Sol Ring", "Urza's Saga", "Saga"))
    assert matcher.match("SOL RING and Urza's Saga; a ringside event.") == [
        "Sol Ring", "Urza's Saga"
    ]


def test_catalog_is_persisted_and_used_without_refresh_when_fresh(tmp_path: Path) -> None:
    provider = CatalogProvider(["Lightning Bolt", "Sol Ring"])
    path = tmp_path / "catalog.json"
    first = asyncio.run(CardCatalog(path, provider).get())
    second = asyncio.run(CardCatalog(path, provider).get())
    assert first.names == second.names == ("Lightning Bolt", "Sol Ring")
    assert not first.stale and not second.stale
    assert provider.calls == 1


def test_catalog_is_not_refreshed_before_one_week(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({
        "source": "oracle_cards",
        "verified_at": (datetime.now(timezone.utc) - timedelta(days=6)).isoformat(),
        "names": ["Sol Ring"],
    }), encoding="utf-8")
    provider = CatalogProvider()
    snapshot = asyncio.run(CardCatalog(path, provider).get())
    assert snapshot.names == ("Sol Ring",)
    assert not snapshot.stale
    assert provider.calls == 0


def test_background_refresh_starts_without_a_question(tmp_path: Path) -> None:
    async def exercise() -> None:
        completed = asyncio.Event()

        class SignallingProvider(CatalogProvider):
            async def get_card_names(self) -> list[str]:
                completed.set()
                return await super().get_card_names()

        provider = SignallingProvider(["Sol Ring"])
        catalog = CardCatalog(tmp_path / "catalog.json", provider)
        catalog.start_background_refresh()
        try:
            await asyncio.wait_for(completed.wait(), timeout=2)
            assert (await catalog.get()).names == ("Sol Ring",)
            assert provider.calls == 1
        finally:
            await catalog.close()

    asyncio.run(exercise())


def test_background_refresh_is_scheduled_at_the_weekly_deadline(tmp_path: Path, monkeypatch) -> None:
    delays: list[float] = []

    async def record_delay(seconds: float) -> None:
        delays.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr("app.services.card_extraction.asyncio.sleep", record_delay)
    catalog = CardCatalog(tmp_path / "catalog.json", CatalogProvider(["Sol Ring"]))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(catalog._refresh_loop())
    assert 7 * 24 * 60 * 60 - 5 <= delays[0] <= 7 * 24 * 60 * 60


def test_failed_background_refresh_retries_without_replacing_stale_index(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "catalog.json"
    payload = {
        "source": "oracle_cards",
        "verified_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        "names": ["Sol Ring"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    delays: list[float] = []

    async def record_delay(seconds: float) -> None:
        delays.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr("app.services.card_extraction.asyncio.sleep", record_delay)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(CardCatalog(path, CatalogProvider())._refresh_loop())
    assert delays == [3600]
    assert json.loads(path.read_text(encoding="utf-8")) == payload

def test_failed_catalog_refresh_preserves_stale_valid_catalog(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    payload = {
        "source": "oracle_cards",
        "verified_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        "names": ["Lightning Bolt"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    snapshot = asyncio.run(CardCatalog(path, CatalogProvider()).get())
    assert snapshot.names == ("Lightning Bolt",)
    assert snapshot.stale
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_concurrent_requests_use_stale_index_during_failed_refresh(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({
        "source": "oracle_cards",
        "verified_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        "names": ["Sol Ring"],
    }), encoding="utf-8")

    async def exercise() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class SlowProvider(CatalogProvider):
            async def get_card_names(self) -> list[str]:
                self.calls += 1
                started.set()
                await release.wait()
                raise CardProviderError("provider_unavailable", "Unavailable", 503)

        provider = SlowProvider()
        catalog = CardCatalog(path, provider)
        first = asyncio.create_task(catalog.get())
        await asyncio.wait_for(started.wait(), timeout=2)
        stale = await asyncio.wait_for(catalog.get(), timeout=1)
        assert stale.stale and stale.names == ("Sol Ring",)
        release.set()
        assert (await first).stale
        assert all(result.stale for result in await asyncio.gather(*(catalog.get() for _ in range(5))))
        assert provider.calls == 1

    asyncio.run(exercise())


def test_failed_empty_catalog_refresh_is_backed_off(tmp_path: Path) -> None:
    async def exercise() -> None:
        provider = CatalogProvider()
        catalog = CardCatalog(tmp_path / "catalog.json", provider)
        results = await asyncio.gather(*(catalog.get() for _ in range(5)), return_exceptions=True)
        assert all(isinstance(result, CardProviderError) for result in results)
        assert provider.calls == 1

    asyncio.run(exercise())


def test_missing_catalog_and_provider_failure_blocks_extraction(tmp_path: Path) -> None:
    with pytest.raises(CardProviderError) as caught:
        asyncio.run(CardCatalog(tmp_path / "catalog.json", CatalogProvider()).get())
    assert caught.value.code == "card_catalog_unavailable"


def test_invalid_utf8_catalog_is_refreshed(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_bytes(b"\xff")
    provider = CatalogProvider(["Lightning Bolt"])
    snapshot = asyncio.run(CardCatalog(path, provider).get())
    assert snapshot.names == ("Lightning Bolt",)
    assert not snapshot.stale
    assert provider.calls == 1
