import pytest
from app.services.card_lookup import normalize_card_name, similarity, extract_name_candidates


def test_normalize_card_name():
    assert normalize_card_name("  Urza's Saga! ") == "urza's saga"


def test_similarity():
    assert similarity("Blood Moon", "Blood Moon") == 1.0


def test_extract_known_cards():
    names = extract_name_candidates("What happens to Blood Moon with Urza's Saga?")
    assert "Blood Moon" in names
    assert "Urza's Saga" in names


def test_extracts_other_title_case_card_names_but_not_keywords():
    names = extract_name_candidates("How does Sheoldred, the Apocalypse interact with Trample?")
    assert "Sheoldred, the Apocalypse" in names
    assert "Trample" not in names
