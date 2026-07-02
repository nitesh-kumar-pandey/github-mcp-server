"""
config.py — Centralised settings loaded from environment / .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_token: str = ""  # PAT for dev / fallback

    # OAuth
    oauth_redirect_uri: str = "https://github-mcp-server-2.onrender.com/auth/callback"
    
    public_base_url: str = "https://github-mcp-server-2.onrender.com"
    # App
    app_secret_key: str = "change-me-in-production"
    app_env: str = "development"
    app_port: int = 8000

    # Database — default to SQLite for local dev; set PostgreSQL URL in production
    database_url: str = "sqlite:///./github_mcp.db"

    # MCP
    mcp_server_name: str = "github-mcp-server"
    mcp_server_version: str = "2.0.0"

    # Redis URL (for OAuth state store in production; falls back to DB if unset)
    redis_url: str = ""

    # Token encryption key — generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    # JWT settings
    jwt_secret_key: str = "change-me-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # MCP API key (Authorization: Bearer <key>) — optional; leave empty to disable
    mcp_api_key: str = ""

    # CORS allowed origins — comma-separated; defaults to * in dev
    cors_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_cors_origins(self) -> list[str]:
        if self.cors_origins:
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.app_env == "production":
            return ["https://claude.ai"]
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
