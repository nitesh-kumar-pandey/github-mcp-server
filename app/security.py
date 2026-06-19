"""
security.py — Token encryption (Fernet) and JWT session management.
P3, P4
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

settings = get_settings()


# ---------------------------------------------------------------------------
# Fernet token encryption  (P4)
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet | None:
    key = settings.encryption_key
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_token(plaintext: str) -> str:
    """Encrypt a GitHub access token. Raises if ENCRYPTION_KEY is not configured —
    production must never silently store raw GitHub tokens. (Problem 6)"""
    f = _get_fernet()
    if f is None:
        raise RuntimeError(
            "ENCRYPTION_KEY not configured. Set it before storing GitHub tokens — "
            "generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored token. Raises if ENCRYPTION_KEY is not configured. (Problem 6)"""
    f = _get_fernet()
    if f is None:
        raise RuntimeError("ENCRYPTION_KEY not configured. Cannot decrypt stored tokens.")
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Stored token could not be decrypted — ENCRYPTION_KEY may have changed.")


# ---------------------------------------------------------------------------
# JWT sessions  (P3)
# ---------------------------------------------------------------------------

def create_jwt(login: str) -> str:
    """Create a signed JWT for a GitHub login."""
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": login,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> Optional[str]:
    """Decode a JWT and return the login, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Per-user API keys (API_KEY -> GitHub login)
# ---------------------------------------------------------------------------

import hashlib
import secrets as _secrets

API_KEY_PREFIX = "umk_"  # "user mcp key"


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns (full_key, key_hash, key_prefix_for_display).
    Only key_hash is stored in the DB — the full_key is shown once and never persisted.
    """
    raw = _secrets.token_urlsafe(32)
    full_key = f"{API_KEY_PREFIX}{raw}"
    key_hash = hash_api_key(full_key)
    display_prefix = full_key[:12]  # e.g. "umk_aB3dEfG1" for identification
    return full_key, key_hash, display_prefix


def hash_api_key(full_key: str) -> str:
    """SHA-256 hash of an API key for DB storage/lookup (keys are not reversible, unlike JWTs)."""
    return hashlib.sha256(full_key.encode()).hexdigest()
