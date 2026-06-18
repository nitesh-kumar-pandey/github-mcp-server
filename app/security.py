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
    """Encrypt a GitHub access token. Falls back to plaintext if no key set."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored token. Falls back to returning as-is if no key set."""
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # Could be a plaintext token stored before encryption was enabled
        return ciphertext


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
