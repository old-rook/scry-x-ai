from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx


_RULE_LINE = re.compile(r"^(\d{3,4}\.\d+[a-z]?)\.\s*(.*)$", re.IGNORECASE)
_RULE_HEADER = re.compile(r"magic:\s*the gathering\s+comprehensive rules", re.IGNORECASE)
_EFFECTIVE_DATE = re.compile(
    r"(?:effective|in effect)\s+(?:as of\s+)?"
    r"([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[a-z0-9]+")
_REQUIRED_MAJOR_GROUPS = frozenset(range(100, 1000, 100))
_MIN_RULES = 500
_MAX_RULES = 10_000
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_SOURCE_PAGE = "https://magic.wizards.com/en/rules"


class RulesIngestionError(Exception):
    """A safe, classified rules refresh failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _RulesLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._active: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        if href:
            self._active = (href, [values.get("title") or ""])

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._active[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._active is not None:
            href, text = self._active
            self.links.append((href, " ".join(text)))
            self._active = None


class RulesService:
    """Validates, versions, and atomically activates official rules documents."""

    def __init__(
        self,
        storage_dir: Path,
        *,
        source_page_url: str = _SOURCE_PAGE,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.source_page_url = source_page_url
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            transport=transport,
            follow_redirects=True,
            headers={"User-Agent": "Scry-X-AI/0.1.0", "Accept": "text/html,text/plain"},
        )
        self._state_lock = asyncio.Lock()
        self._refreshing = False
        self._background_task: asyncio.Task[None] | None = None
        self._manual_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        tasks = [task for task in (self._background_task, self._manual_task) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()

    def status(self) -> dict:
        state = self._read_state()
        return {
            "status": state.get("status", "not_verified"),
            "latest_known_official": state.get("latest_known_official"),
            "latest_verified_local": state.get("active"),
            "last_attempt_at": state.get("last_attempt_at"),
            "last_verified_at": state.get("last_verified_at"),
            "failure_code": state.get("failure_code"),
            "refresh_in_progress": self._refreshing,
        }

    async def start_background_refresh(self, mode: str, interval_hours: int) -> None:
        if self._background_task is None or self._background_task.done():
            self._background_task = asyncio.create_task(
                self._refresh_loop(mode, interval_hours),
                name="rules-refresh-scheduler",
            )

    async def schedule_manual_refresh(self) -> bool:
        async with self._state_lock:
            if self._refreshing or (
                self._manual_task is not None and not self._manual_task.done()
            ):
                return False
            self._manual_task = asyncio.create_task(
                self.refresh(), name="rules-manual-refresh"
            )
            return True

    async def refresh(self) -> bool:
        async with self._state_lock:
            if self._refreshing:
                return False
            self._refreshing = True
        started = _utcnow()
        previous = self._read_state()
        official = None
        try:
            source_url = await self._discover_source()
            official = await asyncio.to_thread(
                self._known_official, source_url, b"", started
            )
            document = await self._download(source_url)
            official = await asyncio.to_thread(
                self._known_official, source_url, document, started
            )
            official = await asyncio.to_thread(
                self._validate_and_activate,
                document,
                source_url,
                started,
                official,
            )
            return True
        except RulesIngestionError as error:
            await asyncio.to_thread(
                self._record_failure, previous, started, error.code, official
            )
            return False
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            await asyncio.to_thread(
                self._record_failure, previous, started, "refresh_failed", official
            )
            return False
        finally:
            async with self._state_lock:
                self._refreshing = False

    async def _refresh_loop(self, mode: str, interval_hours: int) -> None:
        loop = asyncio.get_running_loop()
        next_refresh_at = loop.time() + interval_hours * 60 * 60
        if self._is_stale():
            await self.refresh()
        if mode != "local":
            return
        while True:
            await asyncio.sleep(max(0.0, next_refresh_at - loop.time()))
            next_refresh_at += interval_hours * 60 * 60
            await self.refresh()

    def _is_stale(self) -> bool:
        state = self._read_state()
        verified = state.get("last_verified_at")
        if not verified:
            return True
        try:
            timestamp = datetime.fromisoformat(verified)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return _utcnow() - timestamp > timedelta(hours=24)
        except (TypeError, ValueError):
            return True

    async def _discover_source(self) -> str:
        response = await self._client.get(self.source_page_url)
        response.raise_for_status()
        self._require_wizards_host(str(response.url))
        parser = _RulesLinkParser()
        parser.feed(response.text)
        for href, label in parser.links:
            candidate = urljoin(str(response.url), href)
            path = urlparse(candidate).path.lower()
            description = f"{label} {Path(path).name}".lower()
            if path.endswith(".txt") and (
                "rule" in description or "magiccomprules" in description.replace(" ", "")
            ):
                self._require_wizards_host(candidate)
                return candidate
        raise RulesIngestionError("rules_link_not_found")

    async def _download(self, source_url: str) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async with self._client.stream("GET", source_url) as response:
            response.raise_for_status()
            self._require_wizards_host(str(response.url))
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > _MAX_DOCUMENT_BYTES:
                        raise RulesIngestionError("document_too_large")
                except ValueError:
                    pass
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                size += len(chunk)
                if size > _MAX_DOCUMENT_BYTES:
                    raise RulesIngestionError("document_too_large")
                chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _require_wizards_host(url: str) -> None:
        host = (urlparse(url).hostname or "").lower()
        if urlparse(url).scheme != "https" or not (
            host == "wizards.com" or host.endswith(".wizards.com")
        ):
            raise RulesIngestionError("untrusted_source")

    @staticmethod
    def _parse_document(text: str, source_url: str) -> tuple[str, str, list[dict[str, str]]]:
        if "\x00" in text or not _RULE_HEADER.search(text):
            raise RulesIngestionError("invalid_document")
        date_match = _EFFECTIVE_DATE.search(text[:20_000])
        if date_match is None:
            raise RulesIngestionError("invalid_document")
        date_text = date_match.group(1).replace(",", "")
        try:
            publication_date = (
                date.fromisoformat(date_text)
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text)
                else datetime.strptime(date_text, "%B %d %Y").date()
            ).isoformat()
        except ValueError:
            raise RulesIngestionError("invalid_document") from None

        major_groups: set[int] = set()
        rules: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        for line in text.splitlines():
            rule_match = _RULE_LINE.match(line.strip())
            if rule_match is None:
                if current is not None and line[:1].isspace() and line.strip():
                    current["text"] += " " + line.strip()
                continue
            rule_id, body = rule_match.groups()
            section = rule_id.split(".", 1)[0]
            major_groups.add((int(section) // 100) * 100)
            if current is not None:
                rules.append(current)
            current = {
                "id": rule_id,
                "section": section,
                "text": f"{rule_id}. {body}".strip(),
            }
        if current is not None:
            rules.append(current)
        if not rules or not _REQUIRED_MAJOR_GROUPS.issubset(major_groups):
            raise RulesIngestionError("missing_sections")
        if len({rule["id"] for rule in rules}) != len(rules):
            raise RulesIngestionError("invalid_document")
        if not _MIN_RULES <= len(rules) <= _MAX_RULES:
            raise RulesIngestionError("implausible_rule_count")
        filename = Path(unquote(urlparse(source_url).path)).stem
        date_token = re.search(r"20\d{6}", filename)
        if date_token is not None and date_token.group(0) != publication_date.replace("-", ""):
            raise RulesIngestionError("version_date_mismatch")
        version = date_token.group(0) if date_token else publication_date
        return version, publication_date, rules

    @staticmethod
    def _known_official(source_url: str, document: bytes, discovered_at: datetime) -> dict:
        filename = Path(unquote(urlparse(source_url).path)).stem
        date_token = re.search(r"20\d{6}", filename)
        publication_date = None
        try:
            decoded = document.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            decoded = ""
        date_match = _EFFECTIVE_DATE.search(decoded[:20_000])
        if date_match:
            date_text = date_match.group(1).replace(",", "")
            try:
                publication_date = (
                    date.fromisoformat(date_text)
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text)
                    else datetime.strptime(date_text, "%B %d %Y").date()
                ).isoformat()
            except ValueError:
                publication_date = None
        return {
            "version": date_token.group(0) if date_token else publication_date,
            "publication_date": publication_date,
            "source_url": source_url,
            "discovered_at": discovered_at.isoformat(),
        }

    def _validate_and_activate(
        self,
        document: bytes,
        source_url: str,
        started: datetime,
        official: dict,
    ) -> dict:
        checksum = hashlib.sha256(document).hexdigest()
        try:
            text = document.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            raise RulesIngestionError("invalid_encoding") from None
        version, publication_date, parsed_rules = self._parse_document(text, source_url)
        official = {
            **official,
            "version": version,
            "publication_date": publication_date,
        }
        indexed = self._build_index(parsed_rules)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        data_name = f"rules-{version}-{checksum[:12]}.json"
        text_name = f"source-{version}-{checksum[:12]}.txt"
        self._write_bytes_atomically(self.storage_dir / text_name, document)
        staged_checksum = hashlib.sha256(
            (self.storage_dir / text_name).read_bytes()
        ).hexdigest()
        if staged_checksum != checksum:
            raise RulesIngestionError("checksum_mismatch")
        self._write_bytes_atomically(
            self.storage_dir / data_name,
            json.dumps(
                {
                    "version": version,
                    "publication_date": publication_date,
                    "checksum": checksum,
                    "source_url": source_url,
                    "rules": parsed_rules,
                    "index": indexed,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        verified_at = _utcnow().isoformat()
        manifest = {
            "version": version,
            "publication_date": publication_date,
            "verified_at": verified_at,
            "checksum": checksum,
            "source_url": source_url,
            "rules_file": data_name,
            "source_file": text_name,
            "rule_count": len(parsed_rules),
        }
        # All active and status metadata shares one atomic commit point.
        self._write_json_atomically(
            self.storage_dir / "active.json",
            {
                "format_version": 1,
                "status": "verified",
                "active": manifest,
                "latest_known_official": official,
                "last_attempt_at": started.isoformat(),
                "last_verified_at": verified_at,
                "failure_code": None,
            },
        )
        return official

    @staticmethod
    def _build_index(rules: list[dict[str, str]]) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for rule in rules:
            for token in set(_TOKEN.findall(rule["text"].lower())):
                index.setdefault(token, []).append(rule["id"])
        return index

    def _record_failure(
        self, previous: dict, started: datetime, code: str, official: dict | None
    ) -> None:
        state = {
            **previous,
            "format_version": 1,
            "status": "failed",
            "last_attempt_at": started.isoformat(),
            "failure_code": code,
        }
        if official is not None:
            state["latest_known_official"] = official
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self._write_json_atomically(self.storage_dir / "active.json", state)
        except OSError:
            # Keep the active manifest authoritative if status persistence itself fails.
            pass

    def _read_state(self) -> dict:
        raw = self._read_json(self.storage_dir / "active.json", {})
        if raw.get("format_version") == 1 and "active" in raw:
            return raw

        # Read the former two-file layout without changing or deleting its data.
        legacy_status = self._read_json(self.storage_dir / "status.json", {})
        active = raw if raw.get("version") and raw.get("rules_file") else None
        has_legacy_state = bool(legacy_status or active)
        status_value = legacy_status.get(
            "status", "verified" if active else "not_verified"
        )
        failure_code = legacy_status.get("failure_code")
        if status_value == "verified" and (
            active is None
            or legacy_status.get("last_verified_at") != active.get("verified_at")
        ):
            status_value = "verification_incomplete"
            failure_code = "inconsistent_legacy_state"
        return {
            "format_version": 1,
            "status": status_value if has_legacy_state else "not_verified",
            "active": active,
            "latest_known_official": legacy_status.get("latest_known_official"),
            "last_attempt_at": legacy_status.get("last_attempt_at"),
            "last_verified_at": (active or {}).get("verified_at"),
            "failure_code": failure_code,
        }

    @staticmethod
    def _read_json(path: Path, default):
        try:
            with path.open("r", encoding="utf-8") as file:
                value = json.load(file)
            return value if isinstance(value, dict) else default
        except (OSError, ValueError):
            return default

    @staticmethod
    def _write_bytes_atomically(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
        temporary.replace(path)

    @classmethod
    def _write_json_atomically(cls, path: Path, data: dict) -> None:
        cls._write_bytes_atomically(
            path,
            json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
