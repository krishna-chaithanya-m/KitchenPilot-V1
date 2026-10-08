"""Security utilities: Argon2id password hashing and JWT token management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Any, Dict, Optional

import argon2
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt

from src.api.config import AUTH_ALGORITHM, AUTH_SECRET_KEY, AUTH_TOKEN_EXPIRE_MINUTES

logger = logging.getLogger("kitchenpilot.security")


def hash_token(raw_token: str) -> str:
    """Compute deterministic SHA-256 hexadecimal digest of a raw token.

    In accordance with security requirements, raw verification or reset tokens
    must NEVER be persisted in the database. Only the 64-character SHA-256 digest
    is stored to protect users in the event of database snapshot leaks.
    """
    if not raw_token or not isinstance(raw_token, str):
        raise ValueError("Raw token must be a non-empty string.")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# Initialize Argon2id password hasher with secure production parameters
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False
    except Exception as exc:
        logger.warning("Unexpected error during password verification: %s", exc)
        return False


def create_access_token(
    subject: str | int,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, int]:
    """Create a signed JWT access token.
    
    Returns:
        (token_str, expires_in_seconds)
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
        expires_in = int(expires_delta.total_seconds())
    else:
        expires_in = AUTH_TOKEN_EXPIRE_MINUTES * 60
        expire = now + timedelta(seconds=expires_in)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a signed JWT access token.
    
    Returns payload dictionary or None if invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            AUTH_SECRET_KEY,
            algorithms=[AUTH_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("JWT token has expired.")
        return None
    except jwt.InvalidTokenError as exc:
        logger.debug("JWT token is invalid: %s", exc)
        return None


def verify_google_id_token(id_token_str: str, client_id: Optional[str] = None) -> Dict[str, Any]:
    """Cryptographically verify a Google OAuth 2.0 / OIDC ID token.

    Validates:
    - Token format & signature against Google's public JWKS certificates
    - Issuer: 'accounts.google.com' or 'https://accounts.google.com'
    - Audience: Matches configured GOOGLE_CLIENT_ID
    - Expiration and issued-at timestamps
    - Email presence and email_verified claim is True

    Security Invariants:
    - Never logs raw ID tokens.
    - Never trusts an unverified email claim.
    """
    if not id_token_str or not isinstance(id_token_str, str):
        raise ValueError("Invalid Google ID token.")

    from src.api.config import GOOGLE_AUTH_ENABLED, GOOGLE_CLIENT_ID

    if not GOOGLE_AUTH_ENABLED:
        raise ValueError("Google authentication is disabled.")

    target_client_id = client_id or GOOGLE_CLIENT_ID
    if not target_client_id:
        raise ValueError("Google Client ID is not configured.")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        request = google_requests.Request()
        payload = id_token.verify_oauth2_token(
            id_token_str,
            request,
            audience=target_client_id,
        )
    except Exception as exc:
        logger.warning("Google ID token verification failed: %s", type(exc).__name__)
        raise ValueError("Google ID token verification failed.")

    # Validate issuer
    issuer = payload.get("iss")
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError(f"Invalid Google token issuer: {issuer}")

    # Validate email claim
    email = payload.get("email")
    if not email or not isinstance(email, str):
        raise ValueError("Google ID token does not contain an email address.")

    # Require Google verified email
    email_verified = payload.get("email_verified")
    if not email_verified:
        raise ValueError("Google email address is not verified by Google.")

    # Ensure subject claim is present
    if not payload.get("sub"):
        raise ValueError("Google ID token does not contain a subject claim.")

    return payload
