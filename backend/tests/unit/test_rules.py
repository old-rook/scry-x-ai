from app.services.rules_ingestion import parse_rules, checksum
from app.services.rules_repository import RulesRepository
import tempfile
import os
import shutil


def test_parse_rules_fixture():
    lines = [
        "1. Game Concepts",
        "100.1. These are the rules.",
    ]
    lines.extend(f"{i}.1. Rule text {i}." for i in range(101, 201))
    parsed = parse_rules("\n".join(lines))
    assert len(parsed) >= 100
    assert parsed[0][0] == "100.1"


def test_parser_rejects_too_few_rules():
    try:
        parse_rules("100.1. Only one rule.")
    except ValueError:
        return
    raise AssertionError("Parser did not fail loudly")


def test_checksum_is_deterministic():
    assert checksum("rules") == checksum("rules")
    assert len(checksum("rules")) == 64


def test_exact_rule_number_lookup():
    directory = tempfile.mkdtemp()
    try:
        path = os.path.join(directory, "rules.db")
        repo = RulesRepository(path)
        repo.initialize()
        repo.ensure_sample_version()
        retrieved = repo.retrieve("What does rule 305.7 mean?")
        assert retrieved
        assert retrieved[0].rule_id == "305.7"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_keyword_query_retrieves_only_relevant_rules():
    directory = tempfile.mkdtemp()
    try:
        repo = RulesRepository(os.path.join(directory, "rules.db"))
        repo.initialize()
        retrieved = repo.retrieve("How does Deathtouch with Trample work?")
        assert {rule.rule_id for rule in retrieved} == {
            "702.2b", "702.2c", "702.19a", "702.19b",
        }
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_unmatched_question_does_not_return_unrelated_rules():
    directory = tempfile.mkdtemp()
    try:
        repo = RulesRepository(os.path.join(directory, "rules.db"))
        repo.initialize()
        assert repo.retrieve("What is the best deck for this format?") == []
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_migrates_placeholder_rules_to_curated_excerpts():
    directory = tempfile.mkdtemp()
    try:
        repo = RulesRepository(os.path.join(directory, "rules.db"))
        repo.initialize()
        with repo.connect() as con:
            con.execute(
                "INSERT INTO rules_versions VALUES (?, ?, ?, ?, ?, 'active')",
                ("cr-mvp-local", "https://example.invalid", None, "old", "placeholder"),
            )
            con.execute(
                "INSERT INTO rules VALUES (?, ?, ?, ?, ?, ?)",
                ("100.1", None, "General", "Placeholder data.", "cr-mvp-local", "old"),
            )
        version = repo.ensure_sample_version()
        rules = repo.retrieve("Deathtouch and Trample")
        assert version["version_id"] == "cr-curated-2026-11-06"
        assert "100.1" not in {rule.rule_id for rule in repo.retrieve("rule 100.1")}
        assert {rule.rule_id for rule in rules} >= {"702.2c", "702.19b"}
    finally:
        shutil.rmtree(directory, ignore_errors=True)
