import os
import sqlite3
import re
from dataclasses import dataclass


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
        if version:
            return version
        now = "2026-11-21T00:00:00Z"
        version_id = "cr-mvp-local"
        source_url = "https://magic.wizards.com/en/rules"
        with self.connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO rules_versions VALUES (?, ?, ?, ?, ?, 'active')",
                (version_id, source_url, "2026-11-21", now, "local-development",),
            )
            sample_rules = [
                ("100.1", None, "General", "These Magic rules apply to the game."),
                ("103.1", None, "Starting the Game", "The Magic game is a competitive game in which the players play with decks."),
                ("305.7", "305", "Permanents", "If an effect sets a land's subtype to no longer be Basic, the land loses that subtype."),
                ("614.1", None, "Replacement and Triggered Effects", "Some continuous effects modify a card's characteristics."),
                ("614.5", "614", "Replacement and Triggered Effects", "A replacement effect sees an event before it happens."),
            ]
            con.executemany(
                "INSERT OR IGNORE INTO rules VALUES (?, ?, ?, ?, ?, ?)",
                [(r, p, s, t, version_id, now) for r, p, s, t in sample_rules],
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
        number_match = re.search(r"\b(\d{3}(?:\.\d+[a-z]?)?)\b", question)
        number = number_match.group(1) if number_match else None
        with self.connect() as con:
            rows = []
            if number:
                normalized = number.strip(".")
                rows.extend(con.execute(
                    "SELECT * FROM rules WHERE version_id=? AND rule_id LIKE ? LIMIT ?",
                    (version["version_id"], normalized + "%", limit),
                ).fetchall())
            if not rows:
                terms = " OR ".join(
                    t for t in question.replace("?", " ").replace(".", " ").split()
                    if len(t) >= 3
                )
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
            if not rows:
                rows = con.execute(
                    "SELECT * FROM rules WHERE version_id=? LIMIT ?",
                    (version["version_id"], limit),
                ).fetchall()
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
