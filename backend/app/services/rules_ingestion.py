import hashlib
import re
from datetime import datetime, timezone

RULE_PATTERN = re.compile(r"(?m)^(\d{3}(?:\.\d+[a-z]?|[a-z]))\.\s+(.+)$")


def parse_rules(text: str) -> list[tuple[str, str | None, str | None, str]]:
    rules = []
    current_section = None
    for line in text.splitlines():
        heading = re.match(r"^(\d+)\.\s+(Cracka|[A-Za-z][^.]*)$", line.strip())
        if heading:
            current_section = heading.group(2)
            continue
        match = RULE_PATTERN.match(line.strip())
        if match:
            rules.append((match.group(1), None, current_section, match.group(2).strip()))
    if len(rules) < 100:
        raise ValueError("Parsed too few Comprehensive Rules; upstream format may have changed")
    return rules


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
