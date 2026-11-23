import httpx
import pytest

from app.providers.scryfall import ScryfallProvider


@pytest.fixture(autouse=True)
def isolate_background_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("CARD_CATALOG_PATH", str(tmp_path / "card-names.json"))
    get_card_names = ScryfallProvider.get_card_names

    async def isolated_catalog(provider):
        if isinstance(provider._client._transport, httpx.AsyncHTTPTransport):
            return ["Test Card"]
        return await get_card_names(provider)

    monkeypatch.setattr(ScryfallProvider, "get_card_names", isolated_catalog)
