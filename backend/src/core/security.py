"""Argon2id password hashing (pwdlib) and JWT access token creation/verification (PyJWT)."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pydantic import BaseModel, ConfigDict

from src.core.config import get_settings
from src.core.exceptions import AuthenticationFailedError

_password_hasher = PasswordHash((Argon2Hasher(),))


class UserRole(StrEnum):
    """RBAC roles across bravo-erp."""

    OWNER = "OWNER"
    TECHNICIAN = "TECHNICIAN"
    PUBLIC_CLIENT = "PUBLIC_CLIENT"


class TokenPayload(BaseModel):
    """Validated JWT access token claims."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    sub: UUID
    organization_id: UUID
    role: UserRole
    email: str
    full_name: str
    is_demo: bool = False
    exp: int
    iat: int


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an Argon2id hash in constant time."""
    try:
        return _password_hasher.verify(plain_password, password_hash)
    except Exception:
        return False


def create_access_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    role: UserRole,
    email: str,
    full_name: str,
    is_demo: bool = False,
    expires_delta: timedelta | None = None,
) -> str:
    """Encode a signed JWT access token with tenant and RBAC claims."""
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload: dict[str, str | int | bool] = {
        "sub": str(user_id),
        "organization_id": str(organization_id),
        "role": role.value,
        "email": email,
        "full_name": full_name,
        "is_demo": is_demo,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT access token, raising AuthenticationFailedError on failure."""
    settings = get_settings()
    try:
        raw_payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if not isinstance(raw_payload, dict):
            raise AuthenticationFailedError(detail="Invalid JWT token payload structure.")
        return TokenPayload.model_validate(raw_payload)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailedError(detail="Access token has expired.") from exc
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthenticationFailedError(detail="Could not validate credentials.") from exc
