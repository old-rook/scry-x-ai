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
