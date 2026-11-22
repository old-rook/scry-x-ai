"""Bounded, read-only retrieval of verified rules and Scryfall card evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.providers.base import CardProvider
from app.rules.service import RulesService
from app.schemas.cards import CardDetail, CardRuling, CardSearchRequest


MAX_QUESTION_LENGTH = 2_000
MAX_RULE_RESULTS = 8
MAX_RULE_TEXT_LENGTH = 1_200
MAX_TOTAL_RULE_TEXT_LENGTH = 6_000
MAX_CARD_CANDIDATES = 3
MAX_CARD_TEXT_LENGTH = 2_000
MAX_CARD_RULINGS = 8
MAX_RULING_TEXT_LENGTH = 1_000

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_RULE_REFERENCE = re.compile(
    r"(?:(?:comprehensive\s+rules|rules?|cr)\s*)?"
    r"\b(\d{3,4}\.\d+[a-z]?)\b",
    re.IGNORECASE,
)
_RULE_HEADING_ID = re.compile(r"\d{3,4}\.\d+\Z")
_RULE_SECTION_REFERENCE = re.compile(r"\brule\s+(\d{3,4})\b(?!\.\d)", re.IGNORECASE)
_LAND_TYPE_SETTING = re.compile(
    r"\blands?\b[^.;]{0,120}\b(?:are|is|become|becomes)\s+"
    r"(?:a\s+)?(?:plains?|islands?|swamps?|mountains?|forests?)\b",
    re.IGNORECASE,
)
_QUOTED_NAME = re.compile(r"""["“]([^"”\n]{1,100})["”]""")
_TITLE_PHRASE = re.compile(
    r"\b[A-Z][A-Za-z'’\-]*(?:\s+(?:(?:of|the|and|to|for|in|on|at|with|from|into|by|a|an)\s+)?"
    r"[A-Z][A-Za-z'’\-]*)*\b"
)
_TITLE_CONNECTORS = frozenset(
    {"of", "the", "and", "to", "for", "in", "on", "at", "with", "from", "into", "by", "a", "an"}
)
_SINGLE_WORD_CARD_CUE = re.compile(
    r"\b(?i:can|could|does|do|did|is|are|was|were|would|should|will|what|when|where|why|"
    r"how|which|who|about|with|using|use|on)\s+((?-i:[A-Z])[A-Za-z'’\-]*)\b",
)
_QUESTION_PREFIXES = frozenset(
    {
        "can", "could", "does", "do", "did", "is", "are", "was", "were", "would",
        "should", "will", "what", "when", "where", "why", "how", "which", "who",
        "explain", "tell", "show", "describe",
    }
)
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
        "do", "does", "for", "from", "has", "have", "how", "i", "if", "in", "is",
        "it", "of", "on", "or", "that", "the", "their", "then", "this", "to",
        "was", "what", "when", "where", "which", "who", "will", "with", "would",
    }
)


@dataclass(frozen=True)
class RuleEvidence:
    rule_id: str
    text: str


@dataclass(frozen=True)
class CardEvidence:
    evidence_id: str
    name: str
    type_line: str | None
    oracle_text: str | None
    scryfall_uri: str | None = None
    rulings: tuple[CardRuling, ...] = ()
    source: str = "scryfall"


@dataclass(frozen=True)
class EvidenceBundle:
    rules: tuple[RuleEvidence, ...] = ()
    cards: tuple[CardEvidence, ...] = ()
    ruleset_metadata: dict[str, str] | None = None


def extract_card_name_candidates(question: str) -> list[str]:
    """Extract a small set of title-like names without making semantic claims."""
    bounded_question = question[:MAX_QUESTION_LENGTH]
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str, *, quoted: bool = False) -> None:
        normalized = " ".join(candidate.strip().split()).strip(" ,.!?:;()[]{}")
        if not normalized or len(normalized) > 100:
            return
        words = normalized.split()
        if words and words[0].casefold() in _QUESTION_PREFIXES:
            words = words[1:]
            normalized = " ".join(words)
        if not normalized or (len(words) < 2 and not quoted):
            return
        key = normalized.casefold()
        if key not in seen and len(candidates) < MAX_CARD_CANDIDATES:
            seen.add(key)
            candidates.append(normalized)

    for match in _QUOTED_NAME.finditer(bounded_question):
        add(match.group(1), quoted=True)
    for match in _TITLE_PHRASE.finditer(bounded_question):
        phrase = match.group(0)
        words = phrase.split()
        while words and words[0].casefold() in _QUESTION_PREFIXES:
            words.pop(0)
        while words and words[-1].casefold() in _TITLE_CONNECTORS:
            words.pop()
        add(" ".join(words))
        if len(candidates) >= MAX_CARD_CANDIDATES:
            break
    for match in _SINGLE_WORD_CARD_CUE.finditer(bounded_question):
        candidate = match.group(1)
        if any(candidate.casefold() in item.casefold().split() for item in candidates):
            continue
        add(candidate, quoted=True)
        if len(candidates) >= MAX_CARD_CANDIDATES:
            break
    return candidates


async def retrieve_evidence(
    question: str,
    rules_service: RulesService,
    card_provider: CardProvider,
) -> EvidenceBundle:
    """Retrieve bounded verified evidence; this function never stores the question."""
    if not isinstance(question, str):
        return EvidenceBundle()
    bounded_question = question[:MAX_QUESTION_LENGTH]
    snapshot = rules_service.read_verified_rules_snapshot()
    if snapshot is None:
        verified_rules = None
        metadata = None
    else:
        verified_rules, metadata = snapshot
    cards = await _retrieve_cards(bounded_question, card_provider)
    rules = _retrieve_rules(bounded_question, verified_rules, cards)
    return EvidenceBundle(
        rules=tuple(rules),
        cards=tuple(cards),
        ruleset_metadata=metadata,
    )


def _retrieve_rules(
    question: str,
    verified_rules: list[dict[str, str]] | None,
    cards: list[CardEvidence] | None = None,
) -> list[RuleEvidence]:
    if not verified_rules:
        return []
    by_id = {rule["id"].casefold(): rule for rule in verified_rules}
    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()

    for match in _RULE_REFERENCE.finditer(question):
        rule = by_id.get(match.group(1).casefold())
        if rule is not None and rule["id"].casefold() not in selected_ids:
            selected.append(rule)
            selected_ids.add(rule["id"].casefold())
            if len(selected) >= MAX_RULE_RESULTS:
                return _bound_rule_text(selected)

    card_rule_ids = _card_rule_hints(cards or [])
    added_card_rule = False
    for rule_id in card_rule_ids:
        rule = by_id.get(rule_id.casefold())
        if rule is not None and rule["id"].casefold() not in selected_ids:
            selected.append(rule)
            selected_ids.add(rule["id"].casefold())
            added_card_rule = True
            if len(selected) >= MAX_RULE_RESULTS:
                return _bound_rule_text(selected)
    if added_card_rule:
        return _bound_rule_text(selected)

    query_terms = _normalized_terms(question)
    rule_terms = {
        rule["id"].casefold(): _normalized_terms(rule["text"])
        for rule in verified_rules
    }
    topic_candidates: list[tuple[str, set[str]]] = []
    topic_rules: list[dict[str, str]] = []
    for rule in verified_rules:
        rule_id = rule["id"]
        if not _RULE_HEADING_ID.fullmatch(rule_id):
            continue
        prefix = f"{rule_id}."
        if not rule["text"].startswith(prefix):
            continue
        heading_terms = _normalized_terms(rule["text"][len(prefix) :])
        if not heading_terms or not heading_terms.issubset(query_terms):
            continue
        topic_candidates.append((rule_id, heading_terms))

    for rule_id, terms in topic_candidates:
        root = rule_id.casefold()
        if any(
            terms < other_terms
            for other_root, other_terms in topic_candidates
            if other_root.casefold() != root
        ):
            continue
        children = [
            candidate
            for candidate in verified_rules
            if re.fullmatch(re.escape(rule_id) + r"[a-z]", candidate["id"], re.IGNORECASE)
        ]
        children.sort(key=lambda candidate: candidate["id"].casefold())
        topic_rules.extend(children[:2])

    for rule in topic_rules:
        rule_key = rule["id"].casefold()
        if rule_key not in selected_ids:
            selected.append(rule)
            selected_ids.add(rule_key)
            if len(selected) >= MAX_RULE_RESULTS:
                return _bound_rule_text(selected)

    topic_term_sets: list[set[str]] = []
    referenced_sections: set[str] = set()
    for rule in topic_rules:
        topic_term_sets.append(rule_terms[rule["id"].casefold()])
        referenced_sections.update(_RULE_SECTION_REFERENCE.findall(rule["text"]))
    topic_terms = set.intersection(*topic_term_sets) if topic_term_sets else set()
    support_terms = topic_terms - query_terms

    def relevance_score(terms: set[str]) -> tuple[int, int]:
        return (
            len(query_terms.intersection(terms)),
            len(support_terms.intersection(terms)),
        )

    assigning_combat_damage = {"assign", "combat", "damage"}.issubset(topic_terms)
    related_rules = [
        rule
        for rule in verified_rules
        if rule["section"] in referenced_sections
        and rule["id"].casefold() not in selected_ids
        and (
            not assigning_combat_damage
            or re.fullmatch(
                re.escape(rule["section"]) + r"\.1[a-z]",
                rule["id"],
                re.IGNORECASE,
            )
        )
    ]
    related_rules.sort(
        key=lambda rule: (
            -relevance_score(rule_terms[rule["id"].casefold()])[0],
            -relevance_score(rule_terms[rule["id"].casefold()])[1],
            rule["id"].casefold(),
        )
    )
    for rule in related_rules[: 2 if assigning_combat_damage else 1]:
        selected.append(rule)
        selected_ids.add(rule["id"].casefold())
        if len(selected) >= MAX_RULE_RESULTS:
            return _bound_rule_text(selected)

    if any("lethal" in terms for terms in topic_term_sets):
        lethal_definitions = [
            rule
            for rule in verified_rules
            if {"lethal", "toughness"}.issubset(rule_terms[rule["id"].casefold()])
            and rule["id"].casefold() not in selected_ids
        ]
        lethal_definitions.sort(
            key=lambda rule: rule["id"].casefold()
        )
        for rule in lethal_definitions[:1]:
            selected.append(rule)
            selected_ids.add(rule["id"].casefold())
            if len(selected) >= MAX_RULE_RESULTS:
                return _bound_rule_text(selected)

    if topic_rules:
        return _bound_rule_text(selected)

    relevant: list[tuple[int, str, dict[str, str]]] = []
    for rule in verified_rules:
        rule_key = rule["id"].casefold()
        if rule_key in selected_ids:
            continue
        terms = rule_terms[rule_key]
        overlap = len(query_terms.intersection(terms))
        if overlap:
            relevant.append((overlap, rule["id"], rule))
    relevant.sort(key=lambda result: (-result[0], result[1].casefold()))
    selected.extend(
        rule for _, _, rule in relevant[: MAX_RULE_RESULTS - len(selected)]
    )
    return _bound_rule_text(selected)


def _card_rule_hints(cards: list[CardEvidence]) -> tuple[str, ...]:
    if not any(_LAND_TYPE_SETTING.search(card.oracle_text or "") for card in cards):
        return ()

    rule_ids = ["305.7", "305.8", "613.1d"]
    if any(
        card.type_line and "saga" in _normalized_terms(card.type_line)
        for card in cards
    ):
        rule_ids.extend(("715.2", "715.3", "715.4"))
    return tuple(rule_ids)


def _normalized_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in _TOKEN.findall(text):
        term = token.casefold()
        if term[0].isdigit():
            continue
        if term not in {"blocked", "blocking"} and len(term) > 6 and term.endswith("ing"):
            term = term[:-3]
        elif term not in {"blocked", "blocking"} and len(term) > 5 and term.endswith("ed"):
            term = term[:-2]
        elif len(term) > 4 and term.endswith("ies"):
            term = term[:-3] + "y"
        elif len(term) > 4 and term.endswith("s") and not term.endswith(("ss", "ness", "us", "is")):
            term = term[:-1]
        if len(term) > 2 and term not in _STOPWORDS:
            terms.add(term)
    return terms


def _bound_rule_text(rules: list[dict[str, str]]) -> list[RuleEvidence]:
    evidence: list[RuleEvidence] = []
    total_length = 0
    for rule in rules[:MAX_RULE_RESULTS]:
        remaining = MAX_TOTAL_RULE_TEXT_LENGTH - total_length
        if remaining <= 0:
            break
        text = rule["text"][: min(MAX_RULE_TEXT_LENGTH, remaining)]
        if not text:
            continue
        evidence.append(RuleEvidence(rule_id=rule["id"], text=text))
        total_length += len(text)
    return evidence


async def _retrieve_cards(question: str, card_provider: CardProvider) -> list[CardEvidence]:
    evidence: list[CardEvidence] = []
    for candidate in extract_card_name_candidates(question):
        request = CardSearchRequest(q=f'!"{candidate}"', limit=5)
        response = await card_provider.search_cards(request)
        match = next(
            (card for card in response.cards if card.name.casefold() == candidate.casefold()),
            None,
        )
        if match is None:
            continue
        detail = await card_provider.get_card(match.id)
        if detail.id != match.id or detail.name.casefold() != candidate.casefold():
            continue
        evidence.append(_card_evidence(detail, len(evidence)))
    return evidence


def _card_evidence(card: CardDetail, index: int) -> CardEvidence:
    return CardEvidence(
        evidence_id=f"card:{index}:oracle",
        name=card.name[:100],
        type_line=card.type_line[:300] if card.type_line else None,
        oracle_text=card.oracle_text[:MAX_CARD_TEXT_LENGTH] if card.oracle_text else None,
        scryfall_uri=str(card.scryfall_uri) if card.scryfall_uri else None,
        rulings=tuple(
            ruling.model_copy(update={"comment": ruling.comment[:MAX_RULING_TEXT_LENGTH]})
            for ruling in card.rulings[:MAX_CARD_RULINGS]
        ),
    )
