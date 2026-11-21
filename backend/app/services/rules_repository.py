import hashlib
import os
import sqlite3
import re
from dataclasses import dataclass
from .builtin_rules import (
    BUILTIN_RULES,
    SOURCE_URL,
    SOURCE_VERSION_DATE,
    rule_ids_for_question,
)


@dataclass
class Rule:
    evidence_id: str
    rule_id: str
    text: str
    section: str | None
    version_id: str
    source_url: str


class RulesRepository:
    def __init__(self, path: str):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS rules_versions (
                  version_id TEXT PRIMARY KEY,
                  source_url TEXT NOT NULL,
                  source_version_date TEXT,
                  fetched_at TEXT NOT NULL,
                  checksum_sha256 TEXT NOT NULL,
                  status TEXT NOT NULL CHECK(status IN ('staged','active','retired'))
                );
                CREATE TABLE IF NOT EXISTS rules (
                  rule_id TEXT PRIMARY KEY,
                  parent_rule_id TEXT,
                  section TEXT,
                  rule_text TEXT NOT NULL,
                  version_id TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(version_id) REFERENCES rules_versions(version_id)
                );
                CREATE TABLE IF NOT EXISTS cards_cache (
                  oracle_id TEXT PRIMARY KEY, name TEXT NOT NULL, type_line TEXT,
                  mana_cost TEXT, oracle_text TEXT, image_uri TEXT, scryfall_id TEXT NOT NULL,
                  source_updated_at TEXT, fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rulings_cache (
                  ruling_id TEXT PRIMARY KEY, oracle_id TEXT NOT NULL, published_at TEXT,
                  comment TEXT NOT NULL, fetched_at TEXT NOT NULL
                );
                """
            )
            try:
                con.execute(
                    "CREATE VIRTUAL TABLE rules_fts USING fts5(rule_id, section, rule_text)"
                )
            except sqlite3.OperationalError:
                pass

    def active_version(self) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM rules_versions WHERE status='active' LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def ensure_sample_version(self) -> dict:
        version = self.active_version()
        if version and version["version_id"] != "cr-mvp-local":
            return version
        now = "2026-11-21T00:00:00Z"
        version_id = "cr-curated-2026-11-06"
        checksum = hashlib.sha256(
            "\n".join(rule.summary for rule in BUILTIN_RULES).encode("utf-8")
        ).hexdigest()
        with self.connect() as con:
            if version:
                con.execute("DELETE FROM rules WHERE version_id=?", (version["version_id"],))
                con.execute(
                    "UPDATE rules_versions SET source_url=?, source_version_date=?, "
                    "fetched_at=?, checksum_sha256=? WHERE version_id=?",
                    (SOURCE_URL, SOURCE_VERSION_DATE, now, checksum, version["version_id"]),
                )
                con.execute(
                    "UPDATE rules_versions SET version_id=? WHERE version_id=?",
                    (version_id, version["version_id"]),
                )
            else:
                con.execute(
                    "INSERT INTO rules_versions VALUES (?, ?, ?, ?, ?, 'active')",
                    (version_id, SOURCE_URL, SOURCE_VERSION_DATE, now, checksum),
                )
            con.executemany(
                "INSERT OR REPLACE INTO rules VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        rule.rule_id,
                        rule.parent_rule_id,
                        rule.section,
                        rule.summary,
                        version_id,
                        now,
                    )
                    for rule in BUILTIN_RULES
                ],
            )
        self.initialize_fts()
        return self.active_version() or {}

    def initialize_fts(self) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM rules_fts")
            con.execute(
                "INSERT INTO rules_fts(rule_id, section, rule_text) "
                "SELECT rule_id, section, rule_text FROM rules"
            )

    def retrieve(self, question: str, limit: int = 8) -> list[Rule]:
        version = self.ensure_sample_version()
        number_match = re.search(r"\b(\d{3}(?:\.\d+[a-z]?)?)\b", question, re.IGNORECASE)
        number = number_match.group(1).lower() if number_match else None
        curated_ids = rule_ids_for_question(question)
        with self.connect() as con:
            rows = []
            if number:
                normalized = number.strip(".")
                rows = con.execute(
                    "SELECT * FROM rules WHERE version_id=? AND rule_id LIKE ? "
                    "ORDER BY rule_id LIMIT ?",
                    (version["version_id"], normalized + "%", limit),
                ).fetchall()
            if curated_ids:
                placeholders = ",".join("?" for _ in curated_ids)
                matched = con.execute(
                    f"SELECT * FROM rules WHERE version_id=? AND rule_id IN ({placeholders})",
                    [version["version_id"], *curated_ids],
                ).fetchall()
                by_id = {row["rule_id"]: row for row in matched}
                rows = [by_id[rule_id] for rule_id in curated_ids if rule_id in by_id]
            if not rows:
                stop_words = {
                    "about", "after", "and", "are", "does", "during", "for", "from",
                    "have", "help", "how", "into", "is", "it", "its", "mean", "of",
                    "on", "that", "the", "their", "then", "this", "to", "what", "when",
                    "with", "work", "would",
                }
                terms_found = []
                for term in re.findall(r"[A-Za-z0-9]+", question.lower()):
                    if len(term) >= 3 and term not in stop_words and term not in terms_found:
                        terms_found.append(term)
                terms = " OR ".join(f'"{term}"' for term in terms_found)
                if terms:
                    try:
                        rows = con.execute(
                            "SELECT r.* FROM rules_fts f "
                            "JOIN rules r ON r.rule_id=f.rule_id "
                            "WHERE rules_fts MATCH ? AND r.version_id=? "
                            "ORDER BY bm25(rules_fts) LIMIT ?",
                            (terms, version["version_id"], limit),
                        ).fetchall()
                    except sqlite3.OperationalError:
                        rows = []
            rows = rows[:limit]
        source_url = version["source_url"]
        return [
            Rule(
                evidence_id=f"rule-{row['rule_id'].replace('.', '-')}",
                rule_id=row["rule_id"],
                text=row["rule_text"],
                section=row["section"],
                version_id=row["version_id"],
                source_url=source_url,
            )
            for row in rows
        ]
