"""
SQLAlchemy Database Session Management

Provides async database engine and session factory for both API and Checker services.
"""

import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine
)
from sqlalchemy.pool import NullPool

from .models import Base


def get_database_url() -> str:
    """Build database URL from environment variables."""
    host = os.getenv("DATABASE_HOST", "localhost")
    port = os.getenv("DATABASE_PORT", "5432")
    user = os.getenv("DATABASE_USER", "postgres")
    password = os.getenv("DATABASE_PASSWORD", "postgres")
    database = os.getenv("DATABASE_NAME", "ovh_checker")
    
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


# Global engine and session factory (initialized lazily)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(pool_size: int = 10, max_overflow: int = 20) -> AsyncEngine:
    """
    Get or create the SQLAlchemy async engine.
    
    Args:
        pool_size: Number of connections to keep in the pool
        max_overflow: Maximum connections above pool_size during bursts
    
    Returns:
        AsyncEngine instance
    """
    global _engine
    
    if _engine is None:
        _engine = create_async_engine(
            get_database_url(),
            echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=3600,   # Recycle connections after 1 hour
        )
    
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get the SQLAlchemy async session factory.
    
    Returns:
        async_sessionmaker that creates AsyncSession instances
    """
    global _session_factory
    
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for FastAPI that provides a database session.
    
    Usage in FastAPI:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    
    Yields:
        AsyncSession for database operations
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.
    
    Usage:
        async with session_scope() as session:
            result = await session.execute(select(User))
            ...
    
    Yields:
        AsyncSession for database operations
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Initialize database tables.
    
    This creates all tables defined in the models if they don't exist.
    Use this for development/testing - in production, use migrations.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.
    
    Call this during application shutdown to cleanly close all connections.
    """
    global _engine, _session_factory
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def create_engine_for_worker(pool_class=NullPool) -> AsyncEngine:
    """
    Create a separate engine for background workers.
    
    Workers should use NullPool to avoid connection sharing issues
    with multiprocessing/threading.
    
    Args:
        pool_class: SQLAlchemy pool class (default: NullPool)
    
    Returns:
        New AsyncEngine instance
    """
    return create_async_engine(
        get_database_url(),
        echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
        poolclass=pool_class,
    )


def create_session_factory_for_worker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create a session factory for a worker engine.
    
    Args:
        engine: The worker's AsyncEngine
    
    Returns:
        async_sessionmaker for creating sessions
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
