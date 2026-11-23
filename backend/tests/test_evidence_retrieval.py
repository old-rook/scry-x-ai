import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.providers.scryfall import ScryfallProvider
from app.rules.service import RulesService
from app.schemas.cards import CardSearchResponse
from app.services.evidence_retrieval import (
    MAX_CARD_CANDIDATES,
    MAX_QUESTION_LENGTH,
    MAX_RULE_RESULTS,
    MAX_TOTAL_RULE_TEXT_LENGTH,
    CardResolutionError,
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
                elif rule_section == 700 and number == 5:
                    lines.append(
                        "700.5. Devotion to a color counts that color's mana symbols in permanents' mana costs."
                    )
                else:
                    lines.append(
                        f"{rule_section}.{number}. Sample procedure for section {rule_section}."
                    )
    lines.extend(
        [
            "702.4. Double Strike",
            "702.4a Double strike is a static ability that modifies combat damage rules.",
            "702.4b A creature with double strike deals combat damage in each combat damage step.",
            "702.19. Trample",
            "702.19a Trample modifies how an attacking creature assigns combat damage. (See rule 510, Combat Damage Step.)",
            "702.19b The controller of an attacking creature with trample assigns lethal damage to blockers before assigning excess damage to the player it attacks. This occurs during the same combat damage step.",
            "702.28. Shadow",
            "702.28a Shadow is an evasion ability.",
            "702.28b Creatures with shadow can block only creatures with shadow.",
            "701.6. Counter",
            "701.6a To counter a spell or ability means to cancel it.",
            "701.6b A countered ability doesn't refund costs.",
            "112.1 A spell is a card on the stack.",
            "115.1a The target of an instant spell is chosen as the spell is cast.",
            "117.1a A player may cast an instant spell any time they have priority.",
            "117.3c A player receives priority after casting a spell.",
            "117.3d When a player passes, the next player receives priority.",
            "117.4 If all players pass, the top spell resolves.",
            "601.2c The player chooses an appropriate object for each target.",
            "510.1a Each attacking creature and blocking creature assigns combat damage equal to its power.",
            "510.1c A blocked creature assigns combat damage to the creatures blocking it.",
            "120.6 Damage marked on a creature is lethal if it is equal to or greater than its toughness.",
        ]
    )
    lines.append(
        "601.2f. A spell's targets are chosen as it is cast, and each target must be legal."
    )
    lines.extend(
        [
            "613.1d Layer 4: Type-changing effects are applied.",
            "613.1f Layer 6: Ability-adding and ability-removing effects are applied.",
            "613.1g Layer 7: Power- and toughness-changing effects are applied.",
            "613.4b Layer 7b: Effects set power and toughness to a specific value.",
            "613.5 The application of continuous effects is continually performed.",
            "613.6 An effect applied in one layer continues in later layers even if the ability is removed.",
            "613.7 Effects within the same layer are usually applied in timestamp order.",
            "613.8a An effect may depend on another effect in the same layer.",
            "613.8b Dependent effects wait until the effects they depend on are applied.",
            "700.5a Devotion is calculated before other effects modify characteristics.",
            "305.7 Land subtypes set by an effect replace old land subtypes.",
            "305.8 Lands without the basic supertype are nonbasic.",
            "715.2 A chapter symbol represents a chapter ability.",
            "715.3 Sagas use lore counters to track their progress.",
            "715.4 A Saga with no chapter abilities is not sacrificed by its final chapter.",
            "605.3b An activated mana ability doesn't go on the stack and can't be countered.",
            "605.4a A triggered mana ability doesn't go on the stack and can't be countered.",
        ]
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


def test_mechanic_questions_retrieve_lettered_definition_and_combat_rules(
    tmp_path: Path,
) -> None:
    service = make_rules_service(tmp_path)
    provider = FixtureCardProvider(rows=[])
    try:
        double_strike = asyncio.run(
            retrieve_evidence("What is double strike?", service, provider)
        )
        trample = asyncio.run(
            retrieve_evidence(
                "What happens if my 2/1 Trample gets blocked by a 1/1 creature?",
                service,
                provider,
            )
        )
    finally:
        asyncio.run(service.close())

    double_strike_ids = {rule.rule_id for rule in double_strike.rules}
    trample_ids = {rule.rule_id for rule in trample.rules}
    assert "702.4a" in double_strike_ids
    assert "702.4b" in double_strike_ids
    assert "702.19b" in trample_ids
    assert "510.1c" in trample_ids
    assert "120.6" in trample_ids
    assert provider.queries == []


def test_land_type_changing_effect_with_saga_retrieves_relevant_rules(
    tmp_path: Path,
) -> None:
    blood_moon = {
        "id": "blood-moon-id",
        "name": "Blood Moon",
        "type_line": "Enchantment",
        "oracle_text": "Nonbasic lands are Mountains.",
    }
    urzas_saga = {
        "id": "urzas-saga-id",
        "name": "Urza's Saga",
        "type_line": "Enchantment Land — Urza's Saga",
        "oracle_text": (
            "I — Add {C}. II — Add {C}. III — Search your library for an artifact."
        ),
    }
    service = make_rules_service(tmp_path)
    provider = FixtureCardProvider(rows=[blood_moon, urzas_saga])
    try:
        for question in (
            "What happens when Blood Moon enters with Urza's Saga is on the field?",
            "What happens if Blood Moon enters while Urza's Saga is on the field?",
        ):
            result = asyncio.run(retrieve_evidence(question, service, provider))
            rule_ids = {rule.rule_id for rule in result.rules}
            assert {"305.7", "305.8", "613.1d", "715.2", "715.3", "715.4"} <= rule_ids
            assert len(result.rules) <= MAX_RULE_RESULTS
            assert [card.name for card in result.cards] == ["Blood Moon", "Urza's Saga"]
    finally:
        asyncio.run(service.close())


def test_counterspell_interaction_retrieves_rules_from_card_text(tmp_path: Path) -> None:
    provider = FixtureCardProvider(rows=[
        {
            "id": "dispel-id",
            "name": "Dispel",
            "type_line": "Instant",
            "oracle_text": "Counter target instant spell.",
        },
        {
            "id": "counterspell-id",
            "name": "Counterspell",
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
        },
    ])
    service = make_rules_service(tmp_path)
    try:
        for question in ("Can I Dispel a Counterspell?", ":an I Dispel a Counterspell?"):
            result = asyncio.run(
                retrieve_evidence(question, service, provider, ("Dispel", "Counterspell"))
            )
            assert [card.name for card in result.cards] == ["Dispel", "Counterspell"]
            assert {
                "112.1", "115.1a", "117.1a", "117.3c", "117.3d",
                "117.4", "601.2c", "701.6a",
            } <= {rule.rule_id for rule in result.rules}
    finally:
        asyncio.run(service.close())


@pytest.mark.parametrize(
    ("name", "type_line", "oracle_text"),
    [
        (
            "Darksteel Mutation",
            "Enchantment — Aura",
            "Enchant creature\nEnchanted creature is an Insect artifact creature "
            "with base power and toughness 0/1 and has indestructible, and it loses "
            "all other abilities, card types, and creature types.",
        ),
        (
            "Humility",
            "Enchantment",
            "All creatures lose all abilities and have base power and toughness 1/1.",
        ),
    ],
)
def test_ability_removal_retrieves_continuous_effect_layer_rules(
    tmp_path: Path, name: str, type_line: str, oracle_text: str
) -> None:
    provider = FixtureCardProvider(rows=[
        {
            "id": "bello-id",
            "name": "Bello, Bard of the Brambles",
            "type_line": "Legendary Creature — Raccoon Bard",
            "oracle_text": (
                "During your turn, each non-Equipment artifact and non-Aura enchantment "
                "you control with mana value 4 or greater is a 4/4 Elemental creature "
                "in addition to its other types and has indestructible, haste, and "
                '"Whenever this creature deals combat damage to a player, draw a card."'
            ),
        },
        {
            "id": "ability-removal-id",
            "name": name,
            "type_line": type_line,
            "oracle_text": oracle_text,
        },
    ])
    service = make_rules_service(tmp_path)
    try:
        result = asyncio.run(retrieve_evidence(
            f"Does Bello, Bard of the Brambles still animate artifacts with {name}?",
            service, provider, ("Bello, Bard of the Brambles", name),
        ))
        assert {"613.1d", "613.1f", "613.1g", "613.4b", "613.6"} <= {
            rule.rule_id for rule in result.rules
        }
        assert len(result.rules) <= MAX_RULE_RESULTS
    finally:
        asyncio.run(service.close())


def test_basic_land_conversion_retrieves_dependency_and_devotion_rules(
    tmp_path: Path,
) -> None:
    provider = FixtureCardProvider(rows=[
        {
            "id": "bello-id",
            "name": "Bello, Bard of the Brambles",
            "type_line": "Legendary Creature — Raccoon Bard",
            "oracle_text": (
                "During your turn, each non-Equipment artifact and non-Aura enchantment "
                "you control with mana value 4 or greater is a 4/4 Elemental creature "
                "in addition to its other types and has indestructible, haste, and "
                '"Whenever this creature deals combat damage to a player, draw a card."'
            ),
        },
        {
            "id": "purphoros-id",
            "name": "Purphoros, God of the Forge",
            "type_line": "Legendary Enchantment Creature — God",
            "oracle_text": (
                "Indestructible\nAs long as your devotion to red is less than five, "
                "Purphoros isn't a creature.\nWhenever another creature you control enters, "
                "Purphoros deals 2 damage to each opponent.\n"
                "{2}{R}: Creatures you control get +1/+0 until end of turn."
            ),
        },
        {
            "id": "song-id",
            "name": "Song of the Dryads",
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant permanent\nEnchanted permanent is a colorless Forest land.",
        },
    ])
    service = make_rules_service(tmp_path)
    try:
        result = asyncio.run(retrieve_evidence(
            "I have Bello, Bard of the Brambles and Purphoros, God of the Forge on "
            "the field. An opponent casts Song of the Dryads, targeting my Bello. "
            "During my turn, will Purphoros become a creature?",
            service, provider,
            ("Bello, Bard of the Brambles", "Purphoros, God of the Forge", "Song of the Dryads"),
        ))
        assert {
            "305.7", "613.1d", "613.6", "613.7", "613.8a", "613.8b",
            "700.5", "700.5a",
        } <= {rule.rule_id for rule in result.rules}
        assert len(result.rules) <= MAX_RULE_RESULTS
    finally:
        asyncio.run(service.close())


def test_generic_mana_ability_question_retrieves_relevant_rules_without_card_search(
    tmp_path: Path,
) -> None:
    service = make_rules_service(tmp_path)
    provider = FixtureCardProvider(rows=[])
    try:
        for question in ("Can I counter a mana ability?", "Can I counter a mana abillity?"):
            result = asyncio.run(retrieve_evidence(question, service, provider))
            assert {"605.3b", "605.4a"} <= {rule.rule_id for rule in result.rules}
            assert result.cards == ()
        shadow = asyncio.run(retrieve_evidence("What is shadow?", service, provider))
        assert "702.28a" in {rule.rule_id for rule in shadow.rules}
        assert shadow.cards == ()
        assert provider.queries == []
    finally:
        asyncio.run(service.close())


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


def test_ambiguous_face_name_requires_a_full_card_name(tmp_path: Path) -> None:
    provider = FixtureCardProvider(rows=[
        {"id": "split", "name": "Fire // Ice", "oracle_text": "Split card."},
        {"id": "other", "name": "Fire // Flame", "oracle_text": "Another card."},
    ])
    service = make_rules_service(tmp_path)
    try:
        with pytest.raises(CardResolutionError) as caught:
            asyncio.run(retrieve_evidence("Fire", service, provider, ("Fire",)))
        assert caught.value.suggestions == ("Fire // Ice", "Fire // Flame")
    finally:
        asyncio.run(service.close())


def test_exact_full_card_name_takes_precedence_over_matching_face(tmp_path: Path) -> None:
    provider = FixtureCardProvider(rows=[
        {"id": "split", "name": "Emeritus of Conflict // Lightning Bolt", "oracle_text": "Split card."},
        CARD,
    ])
    service = make_rules_service(tmp_path)
    try:
        result = asyncio.run(retrieve_evidence(
            "Can Lightning Bolt target?", service, provider, ("Lightning Bolt",)
        ))
        assert [card.name for card in result.cards] == ["Lightning Bolt"]
    finally:
        asyncio.run(service.close())
