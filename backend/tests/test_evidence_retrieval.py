import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.providers.scryfall import ScryfallProvider
from app.rules.service import RulesService
from app.schemas.cards import CardSearchResponse
from app.services.evidence_retrieval import (
    MAX_CARD_CANDIDATES,
    MAX_QUESTION_LENGTH,
    MAX_RULE_RESULTS,
    MAX_TOTAL_RULE_TEXT_LENGTH,
    extract_card_name_candidates,
    retrieve_evidence,
)


RULES_URL = "https://media.wizards.com/2026/downloads/MagicCompRules%2020261106.txt"
CARD = {
    "id": "lightning-bolt",
    "name": "Lightning Bolt",
    "type_line": "Instant",
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
}


def rules_document() -> bytes:
    lines = [
        "Magic: The Gathering Comprehensive Rules",
        "These rules are effective as of November 6, 2026.",
        "Introduction",
        "Contents",
    ]
    for section in range(100, 1000, 100):
        sections = range(601, 617) if section == 600 else (section,)
        for rule_section in sections:
            for number in range(1, 66 if section != 600 else 5):
                if rule_section == 601 and number == 2:
                    lines.append(
                        "601.2. To cast a spell, a player chooses its modes, targets, and divisions."
                    )
                else:
                    lines.append(
                        f"{rule_section}.{number}. Sample procedure for section {rule_section}."
                    )
    lines.append(
        "601.2f. A spell's targets are chosen as it is cast, and each target must be legal."
    )
    return "\n".join(lines).encode("utf-8")


def make_rules_service(directory: Path) -> RulesService:
    service = RulesService(
        directory,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, request=request)
        ),
    )
    service._validate_and_activate(
        rules_document(),
        RULES_URL,
        datetime.now(timezone.utc),
        {},
    )
    return service


class FixtureCardProvider:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows if rows is not None else [CARD]
        self.queries: list[str] = []

    async def search_cards(self, request) -> CardSearchResponse:
        self.queries.append(request.q)
        cards = [ScryfallProvider._normalize_card(row) for row in self.rows]
        return CardSearchResponse(cards=cards, total=len(cards))

    async def get_card(self, card_id: str):
        card = next(
            ScryfallProvider._normalize_card(row)
            for row in self.rows
            if row["id"] == card_id
        )
        return card


def test_explicit_and_keyword_rules_are_retrieved_with_output_bounds(tmp_path: Path) -> None:
    service = make_rules_service(tmp_path)
    provider = FixtureCardProvider()
    try:
        result = asyncio.run(
            retrieve_evidence(
                "Can Lightning Bolt target a creature under CR 601.2f?",
                service,
                provider,
            )
        )
    finally:
        asyncio.run(service.close())

    rule_ids = [rule.rule_id for rule in result.rules]
    assert rule_ids[0] == "601.2f"
    assert "601.2" in rule_ids
    assert len(result.rules) <= MAX_RULE_RESULTS
    assert sum(len(rule.text) for rule in result.rules) <= MAX_TOTAL_RULE_TEXT_LENGTH
    assert len(result.cards) == 1
    assert result.cards[0].name == "Lightning Bolt"
    assert result.cards[0].oracle_text == CARD["oracle_text"]
    assert provider.queries == ['!"Lightning Bolt"']


def test_explicit_rule_result_count_is_bounded(tmp_path: Path) -> None:
    service = make_rules_service(tmp_path)
    try:
        question = " ".join(
            f"CR {section}.1" for section in (100, 200, 300, 400, 500, 601, 602, 603, 700, 800)
        )
        result = asyncio.run(
            retrieve_evidence(question, service, FixtureCardProvider(rows=[]))
        )
    finally:
        asyncio.run(service.close())

    assert len(result.rules) == MAX_RULE_RESULTS


def test_unavailable_or_malformed_active_rules_return_no_rule_evidence(tmp_path: Path) -> None:
    unavailable = RulesService(
        tmp_path / "missing",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
    )
    assert unavailable.read_verified_rules() is None

    malformed = make_rules_service(tmp_path / "malformed")
    try:
        state_path = tmp_path / "malformed" / "active.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        rules_path = tmp_path / "malformed" / state["active"]["rules_file"]
        rules_path.write_text("{ malformed", encoding="utf-8")
        result = asyncio.run(
            retrieve_evidence("How are targets chosen?", malformed, FixtureCardProvider())
        )
        assert result.rules == ()

        rules_path.write_text(
            json.dumps({"rules": [{"id": "601.2f", "text": "fabricated"}]}),
            encoding="utf-8",
        )
        assert malformed.read_verified_rules() is None

        state["status"] = "not_verified"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        assert malformed.read_verified_rules() is None
    finally:
        asyncio.run(unavailable.close())
        asyncio.run(malformed.close())


def test_stale_active_rules_are_not_retrieved(tmp_path: Path) -> None:
    service = make_rules_service(tmp_path / "stale")
    state_path = tmp_path / "stale" / "active.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    stale_at = "2020-01-01T00:00:00+00:00"
    state["active"]["verified_at"] = stale_at
    state["last_verified_at"] = stale_at
    state_path.write_text(json.dumps(state), encoding="utf-8")
    try:
        result = asyncio.run(
            retrieve_evidence("How are targets chosen?", service, FixtureCardProvider())
        )
        assert service.read_verified_rules() is None
        assert result.rules == ()
    finally:
        asyncio.run(service.close())


def test_active_rules_are_not_retrieved_if_newer_official_version_is_known(
    tmp_path: Path,
) -> None:
    service = make_rules_service(tmp_path / "superseded")
    state_path = tmp_path / "superseded" / "active.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["latest_known_official"]["version"] = "20261201"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    try:
        result = asyncio.run(
            retrieve_evidence("How are targets chosen?", service, FixtureCardProvider())
        )
        assert service.read_verified_rules() is None
        assert result.rules == ()
    finally:
        asyncio.run(service.close())


def test_candidate_extraction_is_bounded_and_skips_question_words() -> None:
    candidates = extract_card_name_candidates(
        "Can Lightning Bolt target creatures? Does Sol Ring help? What about "
        + ("Repeated Question " * MAX_QUESTION_LENGTH)
    )
    assert candidates[:2] == ["Lightning Bolt", "Sol Ring"]
    assert len(candidates) <= MAX_CARD_CANDIDATES
    assert len(extract_card_name_candidates("a" * (MAX_QUESTION_LENGTH * 2))) == 0
    assert extract_card_name_candidates("Does the creature attack?") == []


def test_common_single_word_card_is_extracted_and_exactly_matched(tmp_path: Path) -> None:
    island = {
        "id": "island-id",
        "name": "Island",
        "type_line": "Basic Land — Island",
        "oracle_text": "{T}: Add {U}.",
    }
    service = make_rules_service(tmp_path)
    provider = FixtureCardProvider(rows=[island])
    try:
        result = asyncio.run(
            retrieve_evidence("Can Island produce blue mana?", service, provider)
        )
    finally:
        asyncio.run(service.close())

    assert extract_card_name_candidates("Can Island produce blue mana?") == ["Island"]
    assert len(result.cards) == 1
    assert result.cards[0].name == "Island"
    assert provider.queries == ['!"Island"']


def test_card_evidence_requires_exact_scryfall_name_match(tmp_path: Path) -> None:
    service = make_rules_service(tmp_path)
    provider = FixtureCardProvider(rows=[{**CARD, "name": "Lightning Bolt Alternate"}])
    try:
        result = asyncio.run(
            retrieve_evidence("Does Lightning Bolt deal damage?", service, provider)
        )
    finally:
        asyncio.run(service.close())

    assert result.cards == ()
    assert provider.queries == ['!"Lightning Bolt"']


def test_no_reliable_candidate_means_no_card_search_or_evidence(tmp_path: Path) -> None:
    service = make_rules_service(tmp_path)
    provider = FixtureCardProvider()
    try:
        result = asyncio.run(retrieve_evidence("How does damage work?", service, provider))
    finally:
        asyncio.run(service.close())

    assert result.cards == ()
    assert provider.queries == []
