import argparse
import httpx
import os
import sqlite3
from app.services.rules_ingestion import parse_rules, checksum, utc_now
from app.services.rules_repository import RulesRepository
from app.core.config import get_settings


def activate(source_url: str, database_path: str) -> dict:
    response = httpx.get(source_url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    text = response.text
    parsed = parse_rules(text)
    digest = checksum(text)
    version_id = f"cr-{digest[:12]}"

    staged_path = database_path + ".staged"
    if os.path.exists(staged_path):
        os.remove(staged_path)
    staged = RulesRepository(staged_path)
    staged.initialize()
    now = utc_now()
    with staged.connect() as con:
        con.execute(
            "INSERT INTO rules_versions VALUES (?, ?, ?, ?, ?, 'staged')",
            (version_id, source_url, None, now, digest),
        )
        con.executemany(
            "INSERT INTO rules VALUES (?, ?, ?, ?, ?, ?)",
            [(rule_id, parent, section, rule_text, version_id, now)
             for rule_id, parent, section, rule_text in parsed],
        )
    staged.initialize_fts()

    os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
    os.replace(staged_path, database_path)
    repo = RulesRepository(database_path)
    repo.initialize()
    with repo.connect() as con:
        con.execute("UPDATE rules_versions SET status='retired' WHERE status='active'")
        con.execute("UPDATE rules_versions SET status='active' WHERE version_id=?", (version_id,))
    return {"version_id": version_id, "checksum_sha256": digest, "rule_count": len(parsed)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--database")
    args = parser.parse_args()
    path = args.database or get_settings().database_path
    print(activate(args.source, path))


if __name__ == "__main__":
    main()
