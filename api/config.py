import os
import logging
from typing import Optional
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _get_jwt_secret() -> str:
    """Get JWT secret, raising error if not set."""
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET environment variable is required. "
            "Generate one with: openssl rand -base64 32"
        )
    return secret


def _get_database_url() -> str:
    """Get database URL, raising error if not set."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:pass@host:5432/dbname"
        )
    return url


def _get_cors_origins() -> str:
    """Get CORS origins with security warning for wildcards."""
    origins = os.getenv("CORS_ORIGINS", "")
    if not origins:
        logger.warning(
            "CORS_ORIGINS not set. For production, set specific origins like "
            "'https://example.com,https://api.example.com'. "
            "Defaulting to same-origin only."
        )
        return ""
    if origins == "*":
        logger.warning(
            "CORS_ORIGINS is set to '*' (allow all). This is insecure for production! "
            "Consider setting specific origins like 'https://example.com'."
        )
    return origins


class Settings(BaseSettings):
    # Database URL - REQUIRED, no default for security
    database_url: str = _get_database_url()
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    cors_origins: str = _get_cors_origins()
    
    # JWT Configuration - REQUIRED, no default for security
    jwt_secret: str = _get_jwt_secret()
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Registration settings
    allow_registration: bool = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"

    class Config:
        env_file = ".env"


settings = Settings()
