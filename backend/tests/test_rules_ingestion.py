import asyncio
import hashlib
import json
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.db.models import User
from app.main import create_app
from app.rules.service import RulesIngestionError, RulesService


SOURCE_PAGE = "https://magic.wizards.com/en/rules"
RULES_URL = "https://media.wizards.com/2026/downloads/MagicCompRules%2020261106.txt"


def run_async(test_function):
    @wraps(test_function)
    def wrapper(*args, **kwargs):
        return asyncio.run(test_function(*args, **kwargs))

    return wrapper


def valid_document() -> bytes:
    lines = [
        "Magic: The Gathering Comprehensive Rules",
        "These rules are effective as of November 6, 2026.",
        "Introduction",
        "Contents",
    ]
    for section in range(100, 900, 100):
        lines.append(f"{section}. Section heading")
        for number in range(1, 66):
            lines.append(f"{section}.{number}. Sample rule text for section {section}.")
            lines.append("    This indented sentence is part of the rule.")
    return "\n".join(lines).encode("utf-8")


def mock_transport(document: bytes, *, rules_url: str = RULES_URL, delay: float = 0):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL(SOURCE_PAGE):
            if delay:
                await asyncio.sleep(delay)
            return httpx.Response(
                200,
                text=f'<a href="{rules_url}">Download Comprehensive Rules</a>',
                request=request,
            )
        if str(request.url) == rules_url:
            return httpx.Response(200, content=document, request=request)
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)


def make_service(tmp_path: Path, document: bytes) -> RulesService:
    return RulesService(tmp_path, transport=mock_transport(document))


@run_async
async def test_valid_document_is_parsed_indexed_checksummed_and_activated(tmp_path: Path) -> None:
    document = valid_document()
    service = make_service(tmp_path, document)

    try:
        assert await service.refresh() is True
        state = json.loads((tmp_path / "active.json").read_text(encoding="utf-8"))
        manifest = state["active"]
        parsed = json.loads((tmp_path / manifest["rules_file"]).read_text(encoding="utf-8"))
        stored_source = (tmp_path / manifest["source_file"]).read_bytes()

        assert manifest["version"] == "20261106"
        assert manifest["publication_date"] == "2026-11-06"
        assert manifest["rule_count"] == 520
        assert manifest["checksum"] == hashlib.sha256(document).hexdigest()
        assert stored_source == document
        assert parsed["rules"][0]["id"] == "100.1"
        assert "indented sentence" in parsed["rules"][0]["text"]
        assert "100.1" in parsed["index"]["sentence"]
        assert service.status()["status"] == "verified"
        assert service.status()["latest_verified_local"]["checksum"] == manifest["checksum"]
    finally:
        await service.close()


@pytest.mark.parametrize(
    ("document", "failure_code"),
    [
        (b"\xff\xfe\x00", "invalid_encoding"),
        (b"not a Comprehensive Rules document", "invalid_document"),
    ],
)
@run_async
async def test_invalid_encoding_and_structure_fail_without_activation(
    tmp_path: Path, document: bytes, failure_code: str
) -> None:
    service = make_service(tmp_path, document)

    try:
        assert await service.refresh() is False
        assert service.status()["latest_verified_local"] is None
        assert service.status()["failure_code"] == failure_code
    finally:
        await service.close()


@run_async
async def test_filename_date_must_match_document_effective_date(tmp_path: Path) -> None:
    mismatched_url = (
        "https://media.wizards.com/2026/downloads/MagicCompRules%2020261107.txt"
    )
    service = RulesService(
        tmp_path,
        transport=mock_transport(valid_document(), rules_url=mismatched_url),
    )
    try:
        assert await service.refresh() is False
        assert service.status()["failure_code"] == "version_date_mismatch"
        assert service.status()["latest_verified_local"] is None
    finally:
        await service.close()


@run_async
async def test_implausible_rule_count_is_rejected(tmp_path: Path) -> None:
    document = valid_document().decode().replace("100.65. Sample rule text for section 100.\n", "")
    # Keep the required sections while remaining below the minimum count.
    for section in range(100, 900, 100):
        for number in range(1, 66):
            if number != 1:
                document = document.replace(
                    f"{section}.{number}. Sample rule text for section {section}.\n"
                    "    This indented sentence is part of the rule.\n",
                    "",
                )
    service = make_service(tmp_path, document.encode())

    try:
        assert await service.refresh() is False
        assert service.status()["failure_code"] == "implausible_rule_count"
        assert service.status()["latest_verified_local"] is None
    finally:
        await service.close()


@run_async
async def test_missing_required_sections_is_rejected(tmp_path: Path) -> None:
    document = "\n".join(
        line for line in valid_document().decode().splitlines()
        if not line.startswith(tuple(f"{section}." for section in range(800, 900)))
    ).encode()
    service = make_service(tmp_path, document)

    try:
        assert await service.refresh() is False
        assert service.status()["failure_code"] == "missing_sections"
    finally:
        await service.close()


@run_async
async def test_official_link_is_recorded_when_document_download_fails(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL(SOURCE_PAGE):
            return httpx.Response(
                200,
                text=f'<a href="{RULES_URL}">Comprehensive Rules</a>',
                request=request,
            )
        return httpx.Response(503, request=request)

    service = RulesService(tmp_path, transport=httpx.MockTransport(handler))
    try:
        assert await service.refresh() is False
        assert service.status()["latest_known_official"]["version"] == "20261106"
        assert service.status()["latest_verified_local"] is None
    finally:
        await service.close()


class TrackedChunkStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.chunks_yielded = 0

    async def __aiter__(self):
        for _ in range(5):
            self.chunks_yielded += 1
            yield b"x" * (64 * 1024)


@run_async
async def test_download_size_limit_is_enforced_during_streaming(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("app.rules.service._MAX_DOCUMENT_BYTES", 100_000)
    stream = TrackedChunkStream()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, request=request)

    service = RulesService(tmp_path, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RulesIngestionError, match="document_too_large"):
            await service._download(RULES_URL)
        assert stream.chunks_yielded == 2
    finally:
        await service.close()


@run_async
async def test_failed_update_preserves_previous_active_ruleset(tmp_path: Path) -> None:
    service = make_service(tmp_path, valid_document())
    try:
        assert await service.refresh() is True
        original_state = json.loads((tmp_path / "active.json").read_text())
        original_manifest = original_state["active"]
    finally:
        await service.close()

    failed_service = make_service(tmp_path, b"\xff")
    try:
        assert await failed_service.refresh() is False
        state_file = json.loads((tmp_path / "active.json").read_text())
        assert state_file["active"] == original_manifest
        state = failed_service.status()
        assert state["failure_code"] == "invalid_encoding"
        assert state["latest_verified_local"] == original_manifest
        assert state["latest_known_official"]["version"] == "20261106"
    finally:
        await failed_service.close()


@run_async
async def test_staged_checksum_mismatch_preserves_previous_active_ruleset(
    tmp_path: Path, monkeypatch
) -> None:
    first = make_service(tmp_path, valid_document())
    try:
        assert await first.refresh() is True
        original_manifest = first.status()["latest_verified_local"]
    finally:
        await first.close()

    changed = valid_document().replace(
        b"Sample rule text for section 100.",
        b"Updated rule text for section 100.",
    )
    service = make_service(tmp_path, changed)
    original_write = service._write_bytes_atomically

    def corrupt_staged_source(path: Path, content: bytes) -> None:
        if path.name.startswith("source-"):
            content = b"corrupted staged source"
        original_write(path, content)

    monkeypatch.setattr(service, "_write_bytes_atomically", corrupt_staged_source)
    try:
        assert await service.refresh() is False
        assert service.status()["failure_code"] == "checksum_mismatch"
        assert service.status()["latest_verified_local"] == original_manifest
    finally:
        await service.close()


@run_async
async def test_manifest_commit_failure_never_reports_candidate_as_active(
    tmp_path: Path, monkeypatch
) -> None:
    first = make_service(tmp_path, valid_document())
    try:
        assert await first.refresh() is True
        original_manifest = first.status()["latest_verified_local"]
    finally:
        await first.close()

    changed = valid_document().replace(
        b"Sample rule text for section 100.",
        b"Updated rule text for section 100.",
    )
    service = make_service(tmp_path, changed)
    original_write = service._write_json_atomically

    def fail_manifest_commit(path: Path, payload: dict) -> None:
        if path.name == "active.json":
            raise OSError("simulated atomic replace failure")
        original_write(path, payload)

    monkeypatch.setattr(service, "_write_json_atomically", fail_manifest_commit)
    try:
        assert await service.refresh() is False
        assert service.status()["latest_verified_local"] == original_manifest
        assert service.status()["latest_verified_local"]["checksum"] == original_manifest["checksum"]
    finally:
        await service.close()


@run_async
async def test_startup_refreshes_when_last_verification_is_stale(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "status.json").write_text(
        json.dumps(
            {
                "status": "verified",
                "last_verified_at": "2026-11-20T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    document = valid_document()
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url == httpx.URL(SOURCE_PAGE):
            return httpx.Response(
                200,
                text=f'<a href="{RULES_URL}">Comprehensive Rules</a>',
                request=request,
            )
        return httpx.Response(200, content=document, request=request)

    service = RulesService(tmp_path, transport=httpx.MockTransport(handler))
    try:
        await service.start_background_refresh("external", 24)
        assert service._background_task is not None
        await service._background_task
        assert requests == [SOURCE_PAGE, RULES_URL]
        assert service.status()["status"] == "verified"
    finally:
        await service.close()


@run_async
async def test_concurrent_refreshes_do_not_duplicate_ingestion(tmp_path: Path) -> None:
    requests: list[str] = []
    document = valid_document()

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url == httpx.URL(SOURCE_PAGE):
            await asyncio.sleep(0.03)
            return httpx.Response(
                200,
                text=f'<a href="{RULES_URL}">Comprehensive Rules</a>',
                request=request,
            )
        return httpx.Response(200, content=document, request=request)

    service = RulesService(tmp_path, transport=httpx.MockTransport(handler))
    try:
        results = await asyncio.gather(service.refresh(), service.refresh())
        assert sorted(results) == [False, True]
        assert requests.count(SOURCE_PAGE) == 1
        assert requests.count(RULES_URL) == 1
    finally:
        await service.close()


def test_admin_rules_status_and_manual_refresh_require_admin(tmp_path: Path) -> None:
    verified_at = datetime.now(timezone.utc).isoformat()
    active_manifest = {
        "version": "20261106",
        "publication_date": "2026-11-06",
        "verified_at": verified_at,
        "checksum": "0" * 64,
        "source_url": RULES_URL,
        "rules_file": "rules-fixture.json",
        "source_file": "source-fixture.txt",
        "rule_count": 520,
    }
    (tmp_path / "active.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "status": "verified",
                "active": active_manifest,
                "last_verified_at": verified_at,
            }
        ),
        encoding="utf-8",
    )
    service = make_service(tmp_path, valid_document())
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        jwt_signing_key="test-signing-key-not-for-production",
        rules_storage_dir=tmp_path,
        rules_refresh_mode="external",
    )
    app = create_app(settings, rules_service=service)
    Base.metadata.create_all(app.state.database.engine)

    with TestClient(app) as client:
        unauthenticated = client.get("/api/v1/admin/rules/status")
        assert unauthenticated.status_code == 401
        user_response = client.post(
            "/api/v1/auth/register",
            json={"email": "rules-user@example.test", "password": "password123"},
        )
        user_token = user_response.json()["access_token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}
        assert client.get("/api/v1/admin/rules/status", headers=user_headers).status_code == 403
        assert client.post("/api/v1/admin/rules/refresh", headers=user_headers).status_code == 403

        with app.state.database.session() as session:
            user = session.get(User, UUID(user_response.json()["user_id"]))
            user.role = "admin"
            session.commit()
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"email": "rules-user@example.test", "password": "password123"},
        )
        admin_headers = {
            "Authorization": f"Bearer {admin_login.json()['access_token']}"
        }
        status_response = client.get("/api/v1/admin/rules/status", headers=admin_headers)
        assert status_response.status_code == 200
        assert status_response.json()["latest_verified_local"]["version"] == "20261106"
        assert "raw" not in status_response.text.lower()

        refresh_response = client.post(
            "/api/v1/admin/rules/refresh", headers=admin_headers
        )
        assert refresh_response.status_code == 202
        assert refresh_response.json() == {"status": "started"}


def test_refresh_interval_cannot_exceed_24_hours() -> None:
    with pytest.raises(ValueError):
        Settings(rules_refresh_interval_hours=25)
