"""Staff PINs, JWTs and the two auth dependencies (§1): staff Bearer tokens and the kiosk header."""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Any

import jwt
from fastapi import Header

from app.config import settings
from app.db import DbSession
from app.errors import ApiError
from app.ids import utcnow
from app.models import Staff

PBKDF2_ROUNDS = 100_000
JWT_ALG = "HS256"
JWT_TTL = timedelta(hours=12)


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def check_pin(pin: str, pin_hash: str) -> bool:
    try:
        salt_hex, digest_hex = pin_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ROUNDS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _secret() -> str:
    if not settings.jwt_secret:
        raise ApiError(500, "server_misconfigured", "JWT_SECRET is not set in .env")
    return settings.jwt_secret


def create_jwt(staff: Staff) -> str:
    now = utcnow()
    claims = {"sub": staff.id, "role": staff.role, "department": staff.department, "iat": now, "exp": now + JWT_TTL}
    return jwt.encode(claims, _secret(), algorithm=JWT_ALG)


def decode_jwt(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALG], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError as exc:
        raise ApiError(401, "unauthorized", "Invalid or expired session — please log in again") from exc


def current_staff(roles: list[str] | None = None) -> Callable[..., Staff]:
    """Dependency factory: `staff: Staff = Depends(current_staff(["doctor"]))`. 401 unauthorized / 403 forbidden."""

    def dependency(db: DbSession, authorization: Annotated[str | None, Header()] = None) -> Staff:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise ApiError(401, "unauthorized", "Log in required")
        claims = decode_jwt(token)
        staff = db.get(Staff, claims["sub"])
        if staff is None or not staff.active:
            raise ApiError(401, "unauthorized", "Staff account not active")
        if roles is not None and staff.role not in roles:
            raise ApiError(403, "forbidden", f"This action needs role: {', '.join(roles)}")
        return staff

    return dependency


def kiosk_id(x_kiosk_id: Annotated[str | None, Header()] = None) -> str:
    """Dependency: the `X-Kiosk-Id` header (KIOSK-01, HALL-01, APP-FOLD, DESK-01)."""
    if not x_kiosk_id or not x_kiosk_id.strip():
        raise ApiError(400, "missing_kiosk_id", "Header X-Kiosk-Id is required")
    return x_kiosk_id.strip()
