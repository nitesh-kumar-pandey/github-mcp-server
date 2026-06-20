"""
main.py — Application entry point.

Fixes applied:
- Problem 1: the two identically-named `mcp_auth_middleware` functions are
  renamed (`jwt_context_middleware` and `mcp_key_middleware`) so the second
  no longer silently overwrites the first.
- Problem 2: mcp_key_middleware now accepts JWT sessions, personal API keys,
  AND the shared MCP_API_KEY, instead of only the shared key (which rejected
  every JWT request).
"""

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
from app.auth import router as auth_router, verify_mcp_request
from app.tools import mcp
from app.user_context import set_current_login, clear_current_login

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
# MCP APP FIRST (IMPORTANT — lifespan must be wired into FastAPI below)
# ---------------------------------------------------------------------------

mcp_app = mcp.http_app(path="/", transport="streamable-http")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

api = FastAPI(
    title="GitHub MCP Server",
    description="""
## GitHub MCP Server v2

A production-ready MCP server exposing GitHub operations as AI-callable tools.

### Connecting Claude
1. Authenticate via `/auth/login` (GitHub OAuth), or
2. Generate a personal API key via `POST /auth/api-keys` and use it directly
3. Use MCP endpoint: `<your-domain>/mcp`
4. Pass `Authorization: Bearer <session-token-or-api-key>`
    """,
    version=settings.mcp_server_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=mcp_app.lifespan,  # required for MCP 1.27+
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

api.state.limiter = limiter
api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
        f"{request.method} {request.url.path} -> {response.status_code} ({elapsed}ms)"
    )
    return response


# ---------------------------------------------------------------------------
# MCP authentication + user-context middleware  (Problem 1 + Problem 2 fix)
#
# Single middleware, single pass, no duplicate function names. Resolves the
# login from JWT session OR personal API key OR shared MCP_API_KEY, then sets
# the request-scoped contextvar so tools can call resolve_token() without an
# explicit `login` argument: API_KEY -> GitHub Login -> tool execution.
# ---------------------------------------------------------------------------

@api.middleware("http")
async def mcp_key_middleware(request: Request, call_next):
    if request.url.path == "/mcp" or request.url.path.startswith("/mcp/"):
        try:
            login = verify_mcp_request(request)  # raises HTTPException(401) if invalid
        except Exception as exc:
            status = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", str(exc))
            return JSONResponse(status_code=status, content={"detail": detail})

        set_current_login(login)  # may be None if only the shared key was used
        try:
            response = await call_next(request)
        finally:
            clear_current_login()
        return response

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
    try:
        create_tables()
        logger.info("DATABASE TABLES CREATED")
    except Exception as e:
        logger.exception(f"DATABASE ERROR: {e}")
        raise

    db_type = (
        "PostgreSQL"
        if settings.database_url.startswith("postgres")
        else "SQLite"
    )

    logger.info(
        f"GitHub MCP Server v{settings.mcp_server_version} — {db_type}"
    )

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
from app.database import create_tables

@api.get("/create-tables")
def create_tables_endpoint():
    create_tables()
    return {"status": "tables created"}





from sqlalchemy import text
from app.database import engine


@api.get("/db-test")
def db_test():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return {
                "database": "connected",
                "result": result.scalar()
            }
    except Exception as e:
        return {
            "database": "failed",
            "error": str(e)
        }
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
    return {"status": "ok", "version": settings.mcp_server_version}

from sqlalchemy import inspect
from app.database import engine

@api.get("/tables")
def tables():
    inspector = inspect(engine)
    return {
        "tables": inspector.get_table_names()
    }
    
from app.database import Base

@api.get("/models")
def models():
    return {
        "models": list(Base.metadata.tables.keys())
    }
    
@api.get("/token-count")
def token_count():
    from app.database import SessionLocal, TokenStore

    db = SessionLocal()
    try:
        return {"count": db.query(TokenStore).count()}
    finally:
        db.close() 

@api.get("/mcp-info")
def mcp_info():
    return {
        "name": settings.mcp_server_name,
        "version": settings.mcp_server_version,
        "transport": "streamable-http",
        "endpoint": "/mcp",
        "auth_required": True,
        "auth_methods": ["jwt_session", "personal_api_key", "shared_mcp_api_key"],
    }


@api.get("/tools", tags=["mcp"])
async def list_tools():
    """List all registered MCP tools."""
    try:
        registered_tools = await mcp.list_tools()
        tools = [getattr(t, "name", str(t)) for t in registered_tools]
        return {"count": len(tools), "tools": tools}
    except Exception as e:
        return {"error": str(e)}


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
