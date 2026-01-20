import os
import secrets
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://ovhchecker:ovhchecker@localhost:5432/ovhchecker"
    )
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    
    # JWT Configuration
    jwt_secret: str = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Registration settings
    allow_registration: bool = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"

    class Config:
        env_file = ".env"


settings = Settings()
