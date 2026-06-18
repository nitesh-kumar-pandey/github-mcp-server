from __future__ import annotations

import sys
import time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from loguru import logger

from app.config import get_settings
from app.database import create_tables
from app.auth import router as auth_router, verify_mcp_key
from app.tools import mcp

settings = get_settings()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger.remove()
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="DEBUG" if settings.app_env == "development" else "INFO",
)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# MCP APP FIRST (IMPORTANT)
# ---------------------------------------------------------------------------

mcp_app = mcp.http_app(
    path="/",
    transport="streamable-http",
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

api = FastAPI(
    title="GitHub MCP Server",
    description="""
## GitHub MCP Server v2

A production-ready MCP server exposing GitHub operations as AI-callable tools.

### Connecting Claude
1. Authenticate via `/auth/login`
2. Use MCP endpoint: `<your-domain>/mcp`
3. Pass `Authorization: Bearer <key>` if enabled
    """,
    version=settings.mcp_server_version,
    docs_url="/docs",
    redoc_url="/redoc",

    # FIX FOR MCP 1.27+
    lifespan=mcp_app.lifespan,
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

api.state.limiter = limiter
api.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

api.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------

@api.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()

    response = await call_next(request)

    elapsed = round((time.time() - start) * 1000, 1)

    logger.info(
        f"{request.method} {request.url.path} → "
        f"{response.status_code} ({elapsed}ms) | "
        f"ip={request.client.host if request.client else 'unknown'}"
    )

    return response

# ---------------------------------------------------------------------------
# MCP API KEY AUTH
# ---------------------------------------------------------------------------

@api.middleware("http")
async def mcp_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        try:
            verify_mcp_key(request)
        except Exception as exc:
            return JSONResponse(
                status_code=401,
                content={"detail": str(exc)}
            )

    return await call_next(request)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

api.include_router(auth_router)

# ---------------------------------------------------------------------------
# Mount MCP
# ---------------------------------------------------------------------------

api.mount("/mcp", mcp_app)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@api.on_event("startup")
def on_startup():
    create_tables()

    db_type = (
        "PostgreSQL"
        if settings.database_url.startswith("postgres")
        else "SQLite"
    )

    logger.info(
        f"✅ GitHub MCP Server v{settings.mcp_server_version} "
        f"— {db_type} — tables ready"
    )

    logger.info(
        f"🔐 Token encryption: "
        f"{'enabled' if settings.encryption_key else 'disabled'}"
    )

    logger.info(
        f"🔑 MCP API key auth: "
        f"{'enabled' if settings.mcp_api_key else 'disabled'}"
    )

    logger.info(
        f"🌐 CORS origins: {settings.get_cors_origins()}"
    )

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@api.get("/")
@limiter.limit("60/minute")
def root(request: Request):
    return {
        "service": settings.mcp_server_name,
        "version": settings.mcp_server_version,
        "status": "running",
        "docs": "/docs",
        "mcp_endpoint": "/mcp",
        "auth": "/auth/login",
    }


@api.get("/health")
def health():
    return {
        "status": "ok",
        "version": settings.mcp_server_version
    }


@api.get("/mcp-info")
def mcp_info():
    return {
        "name": settings.mcp_server_name,
        "version": settings.mcp_server_version,
        "transport": "streamable-http",
        "endpoint": "/mcp",
        "auth_required": bool(settings.mcp_api_key),
    }


@api.get("/tools", tags=["mcp"])
async def list_tools():
    """List all registered MCP tools."""
    try:
        registered_tools = await mcp.list_tools()

        tools = []

        for tool in registered_tools:
            if hasattr(tool, "name"):
                tools.append(tool.name)
            else:
                tools.append(str(tool))

        return {
            "count": len(tools),
            "tools": tools
        }

    except Exception as e:
        return {
            "error": str(e)
        }
# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run_mcp_stdio():
    mcp.run()


def run_http():
    uvicorn.run(
        "app.main:api",
        host="0.0.0.0",
        port=settings.app_port,
        reload=(settings.app_env == "development"),
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stdio":
        run_mcp_stdio()
    else:
        run_http()