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
from sqlalchemy import event, text, inspect, select
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
            # Retry for up to 8 seconds on write-lock contention before raising
            # OperationalError("database is locked"). Default is 0ms (immediate fail).
            # Required because the AI pipeline background task holds the connection
            # open across long-running work (YOLO, Groq network call).
            cursor.execute("PRAGMA busy_timeout=8000")
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


def _sync_schema_columns(sync_conn):
    """
    Dynamically inspects SQLite tables and adds any missing columns defined in ORM models.
    Ensures safe schema evolution without losing existing table data or requiring manual ALTER statements.
    """
    inspector = inspect(sync_conn)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing_cols = {col["name"].lower() for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name.lower() not in existing_cols:
                col_type = column.type.compile(sync_conn.dialect)
                alter_stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}'
                logger.info(
                    "auto_migrating_missing_column",
                    table=table_name,
                    column=column.name,
                    col_type=str(col_type),
                )
                sync_conn.execute(text(alter_stmt))


# ─────────────────────────────────────────────
# Database Initialization
# ─────────────────────────────────────────────
async def init_db() -> None:
    """
    Creates all database tables defined in ORM models.
    Dynamically migrates missing columns for zero-downtime schema evolution.
    Called once at application startup.
    """
    # Import all models here to register them with Base.metadata
    from app import models  # noqa: F401 — import triggers model registration

    from sqlalchemy.exc import OperationalError
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except OperationalError:
            pass
        await conn.run_sync(_sync_schema_columns)

    logger.info(
        "database_initialized",
        database_url=settings.database_url.split("@")[-1],  # Hide credentials in logs
        tables=list(Base.metadata.tables.keys()),
    )

    # Seed the database
    async with AsyncSessionLocal() as session:
        # Check and seed AnganwadiMaster
        result = await session.execute(select(models.AnganwadiMaster))
        if not result.scalars().first():
            logger.info("seeding_anganwadi_master")
            centers = [
                models.AnganwadiMaster(
                    district="Shahdol",
                    block_name="Sohagpur",
                    sector="Jamui (Sohagpur)",
                    supervisor_name="Vandana Panika",
                    supervisor_mobile="9131508182",
                    awc_code="23460060604",
                    center_name="Pongri 1",
                    worker_name="Bhagwati Baiga",
                    worker_mobile="6263302625",
                    registered_children=34,
                    school_going_children=7,
                    latitude="23.2845",  # Demo placeholder until real GPS comes
                    longitude="81.3532"
                ),
                models.AnganwadiMaster(
                    district="Shahdol",
                    block_name="Sohagpur",
                    sector="Jamui (Sohagpur)",
                    supervisor_name="Vandana Panika",
                    supervisor_mobile="9131508182",
                    awc_code="23460060602",
                    center_name="Chapa 1",
                    worker_name="Savitri Singh",
                    worker_mobile="6261756298",
                    registered_children=29,
                    school_going_children=10,
                    latitude="23.2845",
                    longitude="81.3532"
                )
            ]
            session.add_all(centers)
        
        # Check and seed DistrictSettings
        result_settings = await session.execute(select(models.DistrictSettings))
        if not result_settings.scalars().first():
            logger.info("seeding_district_settings")
            ds = models.DistrictSettings(
                district_name="Shahdol",
                collector_name="District Collector",
                collector_mobile="9999999999",
                ceo_name="Shri CEO",
                ceo_mobile="8888888888",
                cdpo_name="Shri Anand Agrawal",
                cdpo_mobile="7777777777",
                official_whatsapp_number="1234567890",
                official_email="contact@bharatos.gov.in"
            )
            session.add(ds)
            
        await session.commit()


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
