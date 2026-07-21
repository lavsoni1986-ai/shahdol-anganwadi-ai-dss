# app/database.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Database Engine, Session Management, and Base Model Setup
# Uses SQLAlchemy 2.0 Async API for non-blocking DB operations.
# MVP: SQLite via aiosqlite | Production: PostgreSQL via asyncpg
# =====================================================================

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# SQLAlchemy Declarative Base
# All ORM models inherit from this Base class.
# ─────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    Declarative base class for all SQLAlchemy ORM models.
    Provides metadata and registry for table definitions.
    """
    pass


# ─────────────────────────────────────────────
# Async Engine Configuration
# ─────────────────────────────────────────────
def _build_engine() -> AsyncEngine:
    """
    Creates and returns the async SQLAlchemy engine.
    Applies SQLite-specific optimizations when using SQLite.
    """
    db_url = settings.database_url

    # Ensure the URL uses the async dialect prefix
    # sqlite → sqlite+aiosqlite  |  postgresql → postgresql+asyncpg
    if db_url.startswith("sqlite:///") and "aiosqlite" not in db_url:
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    elif db_url.startswith("postgresql://") and "asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine_kwargs = {
        "echo": settings.debug,  # Log all SQL statements in debug mode
        "future": True,           # Use SQLAlchemy 2.0 style
    }

    # SQLite-specific: enable WAL mode for better concurrency
    if "sqlite" in db_url:
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_async_engine(db_url, **engine_kwargs)

    # Enable WAL journal mode for SQLite (better concurrency, crash safety)
    if "sqlite" in db_url:
        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


# Create the engine and session factory
engine: AsyncEngine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # Prevent lazy-loading errors after commit
    autocommit=False,
    autoflush=False,
)

# Alias for compatibility with services
async_session_maker = AsyncSessionLocal


# ─────────────────────────────────────────────
# FastAPI Dependency — Database Session
# ─────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides an async database session.
    Session is automatically closed after the request completes,
    even if an exception occurs.

    Usage in route handlers:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────────
# Database Initialization
# ─────────────────────────────────────────────
async def init_db() -> None:
    """
    Creates all database tables defined in ORM models.
    Called once at application startup.
    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
    """
    # Import all models here to register them with Base.metadata
    from app import models  # noqa: F401 — import triggers model registration

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info(
        "database_initialized",
        database_url=settings.database_url.split("@")[-1],  # Hide credentials in logs
        tables=list(Base.metadata.tables.keys()),
    )


async def check_db_health() -> dict:
    """
    Performs a lightweight database health check.
    Returns a dict with status and database URL (sanitized).

    Returns:
        dict: {"status": "healthy"|"unhealthy", "detail": str}
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": settings.database_url.split("///")[-1],
        }
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "detail": str(e),
        }
