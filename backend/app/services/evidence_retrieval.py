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
    rules = _retrieve_rules(bounded_question, verified_rules)
    cards = await _retrieve_cards(bounded_question, card_provider)
    return EvidenceBundle(
        rules=tuple(rules),
        cards=tuple(cards),
        ruleset_metadata=metadata,
    )


def _retrieve_rules(
    question: str, verified_rules: list[dict[str, str]] | None
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

    query_terms = {
        token.casefold()
        for token in _TOKEN.findall(question)
        if len(token) > 2 and token.casefold() not in _STOPWORDS
    }
    relevant: list[tuple[int, str, dict[str, str]]] = []
    for rule in verified_rules:
        rule_key = rule["id"].casefold()
        if rule_key in selected_ids:
            continue
        overlap = len(query_terms.intersection(token.casefold() for token in _TOKEN.findall(rule["text"])))
        if overlap:
            relevant.append((overlap, rule["id"], rule))
    relevant.sort(key=lambda result: (-result[0], result[1].casefold()))
    selected.extend(rule for _, _, rule in relevant[: MAX_RULE_RESULTS - len(selected)])
    return _bound_rule_text(selected)


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
