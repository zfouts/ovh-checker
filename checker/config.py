import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://ovhchecker:ovhchecker@localhost:5432/ovhchecker"
    )
    check_interval_seconds: int = int(os.getenv("CHECK_INTERVAL_SECONDS", "120"))
    notification_threshold_minutes: int = int(os.getenv("NOTIFICATION_THRESHOLD_MINUTES", "60"))
    
    # Distributed mode: Set SUBSIDIARY to run a single-subsidiary checker agent
    # If not set, runs in multi-subsidiary mode (legacy behavior)
    # Examples: SUBSIDIARY=US, SUBSIDIARY=FR, SUBSIDIARY=DE
    subsidiary: Optional[str] = os.getenv("SUBSIDIARY", None)
    
    # Agent identification for logging/monitoring
    agent_id: Optional[str] = os.getenv("AGENT_ID", None)

    class Config:
        env_file = ".env"


settings = Settings()
