"""
database.py — SQLAlchemy engine, session factory, and ORM models.
Supports both SQLite (dev) and PostgreSQL (production).
"""
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from contextlib import contextmanager

from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Engine — PostgreSQL in production, SQLite for local dev
# ---------------------------------------------------------------------------
_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=(settings.app_env == "development"),
    pool_pre_ping=True,  # handles stale connections (important for PG)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Base & Models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class TokenStore(Base):
    """Persists encrypted GitHub OAuth tokens keyed by GitHub login."""

    __tablename__ = "token_store"

    id = Column(Integer, primary_key=True, index=True)
    github_login = Column(String(255), unique=True, nullable=False, index=True)
    encrypted_token = Column(Text, nullable=False)   # P1/P4: encrypted storage
    scope = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OAuthState(Base):
    """Database-backed OAuth state store (replaces in-memory dict). P2"""

    __tablename__ = "oauth_states"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)


class UserSession(Base):
    """JWT session tracking table. P3"""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    github_login = Column(String(255), nullable=False, index=True)
    session_token = Column(String(512), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)


class AuditLog(Base):
    """Lightweight audit trail of MCP tool calls. P10"""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    github_login = Column(String(255), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False)
    params = Column(Text, default="")
    result_summary = Column(Text, default="")
    execution_ms = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_tables() -> None:
    """Create all tables (idempotent)."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Session:  # type: ignore[misc]
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Token store (with encryption) ---

def upsert_token(db: Session, login: str, encrypted_token: str, scope: str = "") -> TokenStore:
    record = db.query(TokenStore).filter_by(github_login=login).first()
    if record:
        record.encrypted_token = encrypted_token
        record.scope = scope
        record.updated_at = datetime.utcnow()
    else:
        record = TokenStore(github_login=login, encrypted_token=encrypted_token, scope=scope)
        db.add(record)
    db.flush()
    return record


def get_encrypted_token(db: Session, login: str) -> str | None:
    record = db.query(TokenStore).filter_by(github_login=login).first()
    return record.encrypted_token if record else None


# --- OAuth state (DB-backed) ---

def store_oauth_state(db: Session, state: str, ttl_seconds: int = 600) -> None:
    expires = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    db.add(OAuthState(state=state, expires_at=expires))
    db.flush()


def consume_oauth_state(db: Session, state: str) -> bool:
    """Return True and mark used if state is valid and unexpired."""
    record = db.query(OAuthState).filter_by(state=state, used=False).first()
    if not record:
        return False
    if record.expires_at < datetime.utcnow():
        return False
    record.used = True
    db.flush()
    return True


def cleanup_expired_states(db: Session) -> None:
    db.query(OAuthState).filter(OAuthState.expires_at < datetime.utcnow()).delete()
    db.flush()


# --- Audit log ---

def log_tool_call(
    db: Session,
    login: str,
    tool_name: str,
    params: str = "",
    result_summary: str = "",
    execution_ms: int = 0,
    success: bool = True,
) -> None:
    db.add(
        AuditLog(
            github_login=login,
            tool_name=tool_name,
            params=params,
            result_summary=result_summary,
            execution_ms=execution_ms,
            success=success,
        )
    )
    db.flush()
