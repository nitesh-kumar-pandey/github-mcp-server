"""
auth.py — GitHub OAuth 2.0 helpers and FastAPI router.
P2: DB-backed OAuth state
P3: JWT cookie sessions
P4: Encrypted token storage
P9: MCP API key auth
"""
from __future__ import annotations
import secrets
import requests
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Cookie
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional

from app.config import get_settings
from app.database import (
    get_db, upsert_token, get_encrypted_token,
    store_oauth_state, consume_oauth_state, cleanup_expired_states,
)
from app.user_context import get_current_login
from app.security import encrypt_token, decrypt_token, create_jwt, decode_jwt
from app.github import get_authenticated_user

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


# ---------------------------------------------------------------------------
# MCP API key dependency  (P9)
# ---------------------------------------------------------------------------

def verify_mcp_key(request: Request) -> None:
    """If MCP_API_KEY is configured, require it on /mcp requests."""
    if not settings.mcp_api_key:
        return  # Auth disabled
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-MCP-KEY", "")
    provided = auth_header.replace("Bearer ", "").strip() or api_key_header.strip()
    if provided != settings.mcp_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing MCP API key")


# ---------------------------------------------------------------------------
# JWT session dependency  (P3)
# ---------------------------------------------------------------------------

def get_current_login(
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = None,
) -> Optional[str]:
    """Extract login from JWT cookie or Authorization header."""
    token = session_token
    if not token and authorization:
        token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None
    return decode_jwt(token)


def require_login(
    session_token: Optional[str] = Cookie(default=None),
) -> str:
    login = get_current_login(session_token=session_token)
    if not login:
        raise HTTPException(status_code=401, detail="Not authenticated. Visit /auth/login")
    return login


# ---------------------------------------------------------------------------
# OAuth Endpoints
# ---------------------------------------------------------------------------

@router.get("/login", summary="Redirect to GitHub OAuth")
def login():
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID not configured")

    state = secrets.token_urlsafe(32)

    # P2: persist state in DB instead of in-memory dict
    with get_db() as db:
        cleanup_expired_states(db)
        store_oauth_state(db, state, ttl_seconds=600)

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "scope": "repo,read:user,user:email",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{query}")


@router.get("/callback", summary="GitHub OAuth callback")
def oauth_callback(code: str, state: str):
    # P2: validate state from DB
    with get_db() as db:
        valid = consume_oauth_state(db, state)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    # Exchange code for token
    token_resp = requests.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.oauth_redirect_uri,
        },
        timeout=15,
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to exchange code with GitHub")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        error = token_data.get("error_description", "Unknown error")
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {error}")

    scope = token_data.get("scope", "")

    # Fetch user info
    user = get_authenticated_user(access_token)

    # P4: encrypt token before storing
    encrypted = encrypt_token(access_token)
    with get_db() as db:
        upsert_token(db, user.login, encrypted, scope)

    # P3: issue JWT session cookie
    jwt_token = create_jwt(user.login)
    response = JSONResponse({
        "message": "Authentication successful",
        "github_login": user.login,
        "scope": scope,
    })
    response.set_cookie(
        key="session_token",
        value=jwt_token,
        httponly=True,
        secure=(settings.app_env == "production"),
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return response


@router.get("/status", summary="Check auth status for a login")
def auth_status(login: str):
    with get_db() as db:
        token = get_encrypted_token(db, login)
    return {"login": login, "authenticated": token is not None}


@router.post("/logout", summary="Clear session cookie")
def logout():
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie("session_token")
    return response


# ---------------------------------------------------------------------------
# Token resolution helper (used by tools.py)
# ---------------------------------------------------------------------------

def resolve_token() -> str:
    login = get_current_login()

    if not login:
        raise RuntimeError(
            "No authenticated GitHub user"
        )

    with get_db() as db:
        enc = get_encrypted_token(db, login)

    if not enc:
        raise RuntimeError(
            f"GitHub account '{login}' not authenticated"
        )

    return decrypt_token(enc)