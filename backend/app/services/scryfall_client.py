import httpx


class ScryfallClient:
    def __init__(self, user_agent: str, timeout: float = 5.0):
        self.user_agent = user_agent
        self.timeout = timeout

    async def exact(self, name: str) -> dict | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                "https://api.scryfall.com/cards/named",
                params={"exact": name},
                headers={"User-Agent": self.user_agent},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
    async def fuzzy(self, name: str) -> dict | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                "https://api.scryfall.com/cards/named",
                params={"fuzzy": name},
                headers={"User-Agent": self.user_agent},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def by_id(self, scryfall_id: str) -> dict | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"https://api.scryfall.com/cards/{scryfall_id}",
                headers={"User-Agent": self.user_agent},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
