"""
auth.py — GitHub OAuth 2.0 helpers and FastAPI router.

Fixes applied:
- Problem 3: JWT sessions are now persisted to the UserSession table.
- Problem 4: decode_jwt() alone is not trusted for /mcp auth — validate_session()
  checks the DB and honors revocation.
- Problem 5: get_user_token() resolves GitHub Login -> Stored Token -> Decrypted Token.
- Per-user API keys: generate/list/revoke endpoints, API_KEY -> GitHub Login resolution.
"""
from __future__ import annotations
import secrets
import requests
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Cookie
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
from app.database import ApiKey, get_db
from app.config import get_settings
from app.database import (
    get_db, upsert_token, get_encrypted_token,
    store_oauth_state, consume_oauth_state, cleanup_expired_states,
    save_session, validate_session, revoke_session,
    create_api_key, list_api_keys, revoke_api_key, resolve_api_key,
)
from app.security import (
    encrypt_token, decrypt_token, create_jwt, decode_jwt,
    generate_api_key, hash_api_key,
)
from app.github import get_authenticated_user

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


# ---------------------------------------------------------------------------
# Auth resolution for /mcp requests
#
# Supports BOTH:
#   Authorization: Bearer <jwt-session-token>   (browser/OAuth login)
#   Authorization: Bearer <umk_api-key>         (per-user API key)
#   Authorization: Bearer <MCP_API_KEY>         (shared server key, optional)
#   X-API-Key: <umk_api-key>                    (alternate header for API keys)
#
# Resolution order: JWT session -> API key -> shared MCP_API_KEY.
# Problem 2 fix: these no longer collide — JWT is checked first via DB-backed
# session validation, and API keys are checked independently by hash lookup.
# ---------------------------------------------------------------------------

def resolve_login_from_request(request: Request) -> Optional[str]:
    """Try to resolve a GitHub login from the incoming request's auth headers.
    Returns None if no valid session/API key is found (does not raise)."""
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    candidate = token or api_key_header.strip()

    if not candidate:
        return None

    # 1. JWT session (DB-validated, honors revocation — Problem 3/4)
    with get_db() as db:
        login = validate_session(db, candidate)
        if login:
            return login

        # 2. Per-user API key
        if candidate.startswith("umk_"):
            key_hash = hash_api_key(candidate)
            login = resolve_api_key(db, key_hash)
            if login:
                return login

    return None


def verify_mcp_request(request: Request) -> Optional[str]:
    """
    Authenticate an incoming /mcp request. Supports JWT sessions, per-user API
    keys, AND the shared MCP_API_KEY (server-level lockdown) at the same time —
    fixing Problem 2 where the old code only ever checked one scheme and
    rejected every JWT request.

    Returns the resolved GitHub login if found (may be None for shared-key-only
    auth, since the shared key isn't tied to a specific user).
    Raises HTTPException(401) if nothing valid is presented.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""

    # Try user-level auth first (JWT session or personal API key)
    login = resolve_login_from_request(request)
    if login:
        return login

    # Fall back to the shared server-level MCP_API_KEY, if configured
    if settings.mcp_api_key and token == settings.mcp_api_key:
        return None  # authenticated, but not tied to a specific GitHub user

    # Nothing matched
    if not settings.mcp_api_key:
        # No shared key configured — user-level auth is required
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide a session token or API key.",
        )
    raise HTTPException(status_code=401, detail="Invalid or missing credentials")


# Kept for backwards compatibility with anything importing verify_mcp_key directly.
def verify_mcp_key(request: Request) -> None:
    verify_mcp_request(request)


# ---------------------------------------------------------------------------
# JWT session dependency (cookie-based, for browser-driven endpoints)
# ---------------------------------------------------------------------------

def get_current_login(session_token: Optional[str] = Cookie(default=None)) -> Optional[str]:
    if not session_token:
        return None
    with get_db() as db:
        return validate_session(db, session_token)


def require_login(session_token: Optional[str] = Cookie(default=None)) -> str:
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
    with get_db() as db:
        valid = consume_oauth_state(db, state)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

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
    user = get_authenticated_user(access_token)

    # Problem 6: encrypt_token now raises if ENCRYPTION_KEY isn't set — surface
    # that clearly instead of silently storing a raw GitHub token.
    try:
        encrypted = encrypt_token(access_token)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    with get_db() as db:
        upsert_token(db, user.login, encrypted, scope)

    # Problem 3: persist the JWT session to the DB, not just sign-and-forget.
    jwt_token = create_jwt(user.login)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    with get_db() as db:
        save_session(db, user.login, jwt_token, expires_at)

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


@router.post("/logout", summary="Clear session cookie and revoke session")
def logout(session_token: Optional[str] = Cookie(default=None)):
    if session_token:
        with get_db() as db:
            revoke_session(db, session_token)
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie("session_token")
    return response


# ---------------------------------------------------------------------------
# Per-user API keys
#
# API_KEY -> GitHub Login
#
# Generate a key while authenticated (browser session); the key can then be
# used directly as a Bearer token against /mcp without needing a login param
# on every tool call — middleware resolves the login before tool execution.
# ---------------------------------------------------------------------------

@router.post("/api-keys", summary="Generate a new personal API key")
def create_new_api_key(name: str = "", session_token: Optional[str] = Cookie(default=None)):
    current_login = get_current_login(session_token=session_token)
    if not current_login:
        raise HTTPException(status_code=401, detail="Not authenticated. Visit /auth/login first.")

    full_key, key_hash, prefix = generate_api_key()
    with get_db() as db:
        create_api_key(db, key_hash=key_hash, key_prefix=prefix, login=current_login, name=name)

    return {
        "api_key": full_key,  # shown once — not retrievable again
        "prefix": prefix,
        "github_login": current_login,
        "message": "Save this key now — it will not be shown again. "
                   "Use it as: Authorization: Bearer <api_key>",
    }


@router.get("/api-keys", summary="List your active API keys")
def get_api_keys(session_token: Optional[str] = Cookie(default=None)):
    current_login = get_current_login(session_token=session_token)
    if not current_login:
        raise HTTPException(status_code=401, detail="Not authenticated. Visit /auth/login first.")

    with get_db() as db:
        keys = list_api_keys(db, current_login)

        return {
            "keys": [
                {
                    "id": k.id,
                    "prefix": k.key_prefix,
                    "name": k.name,
                    "created_at": k.created_at.isoformat(),
                    "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                }
                for k in keys
            ]
        }


@router.delete("/api-keys/{key_id}", summary="Revoke an API key")
def delete_api_key(key_id: int, session_token: Optional[str] = Cookie(default=None)):
    current_login = get_current_login(session_token=session_token)
    if not current_login:
        raise HTTPException(status_code=401, detail="Not authenticated. Visit /auth/login first.")

    with get_db() as db:
        ok = revoke_api_key(db, current_login, key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "id": key_id}


@router.get("/debug-api-key")
def debug_api_key(key: str):
    with get_db() as db:
        key_hash = hash_api_key(key)

        record = (
            db.query(ApiKey)
            .filter_by(key_hash=key_hash, revoked=False)
            .first()
        )

        if not record:
            return {"found": False}

        return {
            "found": True,
            "login": record.github_login,
            "prefix": record.key_prefix,
        }
        
@router.get("/debug-auth")
def debug_auth(request: Request):
    return {
        "authorization": request.headers.get("Authorization"),
        "x_api_key": request.headers.get("X-API-Key"),
    }
    
@router.get("/auth-test")
def auth_test(request: Request):
    login = resolve_login_from_request(request)
    return {"login": login}

# ---------------------------------------------------------------------------
# Token resolution helper (used by tools.py)
#
# Problem 5: GitHub Login -> Stored Token -> Decrypted Token -> GitHub API
# ---------------------------------------------------------------------------

def get_user_token(db, login: str) -> str:
    """Resolve a GitHub login to its decrypted access token. Raises if missing."""
    encrypted = get_encrypted_token(db, login)
    if not encrypted:
        raise RuntimeError(f"No GitHub token stored for {login}")
    return decrypt_token(encrypted)


def resolve_token(login: str | None = None) -> str:
    """
    Resolve the best available GitHub token, in priority order:
    1. The DB-stored OAuth token for `login`, if given (e.g. resolved from
       the request's session/API key by middleware before the tool ran).
    2. The current request-scoped login set by middleware (contextvar).
    3. GITHUB_TOKEN env var (PAT fallback for local dev / single-user mode).
    """
    if login:
        with get_db() as db:
            return get_user_token(db, login)

    from app.user_context import get_current_login as get_ctx_login
    ctx_login = get_ctx_login()
    if ctx_login:
        with get_db() as db:
            return get_user_token(db, ctx_login)

    if settings.github_token:
        return settings.github_token

    raise RuntimeError(
        "No GitHub token available. Authenticate via /auth/login, "
        "pass a personal API key, or set GITHUB_TOKEN in .env"
    )
