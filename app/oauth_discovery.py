from fastapi import APIRouter
from app.config import get_settings

settings = get_settings()
router = APIRouter()

BASE = settings.public_base_url.rstrip("/")

@router.get("/.well-known/oauth-authorization-server")
def oauth_authorization_server():
    return {
        "issuer": BASE,
        "authorization_endpoint": f"{BASE}/authorize",
        "token_endpoint": f"{BASE}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"]
    }


@router.get("/.well-known/oauth-protected-resource")
def oauth_protected_resource():
    return {
        "resource": f"{BASE}/mcp",
        "authorization_servers": [BASE]
    }