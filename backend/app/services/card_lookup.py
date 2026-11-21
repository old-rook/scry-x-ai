import re
from difflib import SequenceMatcher
from .scryfall_client import ScryfallClient


def normalize_card_name(name: str) -> str:
    return re.sub(r"[^\w\s'-]", "", name.lower(), flags=re.UNICODE).strip()


def extract_name_candidates(question: str) -> list[str]:
    known = (
        "Blood Moon", "Urza's Saga", "Darksteel Citadel", "Island", "Forest",
        "Lightning Bolt", "Counterspell", "Ancient Tomb",
    )
    candidates = []
    folded = normalize_card_name(question)
    for name in known:
        if normalize_card_name(name) in folded:
            candidates.append(name)
    return candidates


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_card_name(left), normalize_card_name(right)).ratio()


def normalize_card(payload: dict) -> dict:
    image = payload.get("image_uris") or {}
    return {
        "scryfall_id": payload["id"],
        "oracle_id": payload["oracle_id"],
        "name": payload["name"],
        "type_line": payload.get("type_line"),
        "mana_cost": payload.get("mana_cost"),
        "oracle_text": payload.get("oracle_text"),
        "image_uri": image.get("normal") or image.get("small"),
    }


class CardLookup:
    def __init__(self, client: ScryfallClient):
        self.client = client

    async def identify(self, question: str) -> dict:
        candidates = extract_name_candidates(question)
        if not candidates:
            return {"status": "resolved", "cards": [], "ambiguous": []}

        resolved = []
        ambiguous = []
        for mentioned in candidates:
            exact = await self.client.exact(mentioned)
            if exact:
                card = normalize_card(exact)
                if similarity(mentioned, card["name"]) >= 0.95:
                    resolved.append(card)
                    continue
            fuzzy = await self.client.fuzzy(mentioned)
            if fuzzy:
                card = normalize_card(fuzzy)
                score = similarity(mentioned, card["name"])
                if score >= 0.85:
                    resolved.append(card)
                else:
                    ambiguous.append({"mentioned_name": mentioned, "candidates": [card]})
            else:
                ambiguous.append({"mentioned_name": mentioned, "candidates": []})
        if ambiguous:
            return {"status": "needs_selection", "cards": [], "ambiguous": ambiguous}
        return {"status": "resolved", "cards": resolved, "ambiguous": []}

    async def resolve_confirmed(self, scryfall_ids: list[str]) -> list[dict]:
        cards = []
        for scryfall_id in scryfall_ids:
            try:
                payload = await self.client.by_id(scryfall_id)
                if payload:
                    cards.append(normalize_card(payload))
            except Exception:
                continue
        return cards
