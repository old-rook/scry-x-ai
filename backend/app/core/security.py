from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt

from app.core.config import Settings


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password must be 72 bytes or fewer")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        encoded = password.encode("utf-8")
        if len(encoded) > 72:
            return False
        return bcrypt.checkpw(encoded, password_hash.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return False


def create_access_token(settings: Settings, user_id: UUID, role: str) -> str:
    if settings.jwt_signing_key is None:
        raise RuntimeError("JWT_SIGNING_KEY is not configured")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_lifetime_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_signing_key.get_secret_value(), algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> dict:
    if settings.jwt_signing_key is None:
        raise RuntimeError("JWT_SIGNING_KEY is not configured")
    payload = jwt.decode(
        token,
        settings.jwt_signing_key.get_secret_value(),
        algorithms=["HS256"],
        options={"require": ["sub", "role", "exp", "iat", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    UUID(payload["sub"])
    if payload["role"] not in {"user", "admin"}:
        raise jwt.InvalidTokenError("Invalid role")
    return payload
