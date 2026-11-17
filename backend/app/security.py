"""Password hashing and session tokens."""

from __future__ import annotations

import datetime as dt
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import get_settings

_hasher = PasswordHasher()
SESSION_COOKIE = "session"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


_db_secret: str | None = None


def signing_key() -> str:
    """JWT_SECRET from the environment, else the key generated in the DB."""
    global _db_secret
    env = get_settings().jwt_secret
    if env:
        return env
    if _db_secret is None:
        from sqlalchemy import text

        from .db import engine

        with engine.begin() as conn:
            # created by the migration; recreated here if it was ever removed
            conn.execute(
                text(
                    "INSERT INTO platform_secrets (key, value) VALUES ('jwt_secret', "
                    "replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '')) "
                    "ON CONFLICT (key) DO NOTHING"
                )
            )
            _db_secret = conn.execute(text("SELECT value FROM platform_secrets WHERE key = 'jwt_secret'")).scalar_one()
    return _db_secret


def make_session_token(user_id: int, acting_restaurant_id: int | None = None) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(days=s.session_days)).timestamp()),
    }
    if acting_restaurant_id is not None:
        payload["act"] = acting_restaurant_id
    return jwt.encode(payload, signing_key(), algorithm="HS256")


def read_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, signing_key(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def new_public_token() -> str:
    return secrets.token_urlsafe(16)
