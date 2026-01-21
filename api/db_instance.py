"""Shared database instance for all routers."""
from database import Database
from config import settings

# Shared database instance - connect() called in main.py lifespan
db = Database(settings.database_url)
