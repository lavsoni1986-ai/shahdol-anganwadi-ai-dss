# tests/test_database.py
# P2-A database production-hardening tests: PostgreSQL support, pool config,
# SQLite-only auto-migration, and health-endpoint credential safety.
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# ── 1. asyncpg is declared in requirements.txt ─────────────────────
def test_asyncpg_declared_in_requirements():
    req = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "asyncpg==" in req
    assert "aiosqlite==" in req  # SQLite driver preserved


# ── 2. URL normalization ───────────────────────────────────────────
def test_postgres_url_normalized_to_asyncpg(monkeypatch):
    import app.database as db
    monkeypatch.setattr(db.settings, "database_url", "postgresql://user:pw@host:5432/db")
    engine = db._build_engine()
    assert engine.url.drivername == "postgresql+asyncpg"


def test_sqlite_url_uses_aiosqlite(monkeypatch):
    import app.database as db
    monkeypatch.setattr(db.settings, "database_url", "sqlite:///./test.db")
    engine = db._build_engine()
    assert engine.url.drivername == "sqlite+aiosqlite"


# ── 3. PostgreSQL does not receive SQLite connect_args / PRAGMA ────
def test_postgres_engine_has_no_sqlite_connect_args(monkeypatch):
    import app.database as db
    from sqlalchemy.ext.asyncio import create_async_engine
    recorded = {}

    def _record(url, **kwargs):
        recorded["connect_args"] = kwargs.get("connect_args")
        return create_async_engine(url, **kwargs)

    monkeypatch.setattr(db, "create_async_engine", _record)
    monkeypatch.setattr(db.settings, "database_url", "postgresql+asyncpg://user:pw@host:5432/db")
    db._build_engine()
    assert recorded["connect_args"] is None or "check_same_thread" not in (recorded["connect_args"] or {})


def test_sqlite_engine_has_check_same_thread(monkeypatch):
    import app.database as db
    from sqlalchemy.ext.asyncio import create_async_engine
    recorded = {}

    def _record(url, **kwargs):
        recorded["connect_args"] = kwargs.get("connect_args")
        return create_async_engine(url, **kwargs)

    monkeypatch.setattr(db, "create_async_engine", _record)
    monkeypatch.setattr(db.settings, "database_url", "sqlite+aiosqlite:///./x.db")
    db._build_engine()
    assert recorded["connect_args"] is not None
    assert recorded["connect_args"].get("check_same_thread") is False


# ── 4. PostgreSQL pool configuration applied ───────────────────────
def test_postgres_pool_config_applied(monkeypatch):
    import app.database as db
    monkeypatch.setattr(db.settings, "database_url", "postgresql+asyncpg://user:pw@host:5432/db")
    monkeypatch.setattr(db.settings, "db_pool_size", 4)
    monkeypatch.setattr(db.settings, "db_max_overflow", 8)
    engine = db._build_engine()
    pool = engine.sync_engine.pool
    assert pool._pre_ping is True
    assert pool._max_overflow == 8
    assert pool.size() == 4


# ── 5. SQLite-only auto-migration ──────────────────────────────────
def test_should_auto_migrate_only_for_sqlite():
    import app.database as db
    assert db._should_auto_migrate("sqlite+aiosqlite:///./x.db") is True
    assert db._should_auto_migrate("sqlite:///./x.db") is True
    assert db._should_auto_migrate("postgresql+asyncpg://user:pw@host/db") is False
    assert db._should_auto_migrate("postgresql://user:pw@host/db") is False


def test_database_type_classification():
    import app.database as db
    assert db._database_type("sqlite+aiosqlite:///./x.db") == "sqlite"
    assert db._database_type("postgresql+asyncpg://u:p@h/db") == "postgresql"


# ── 6. Health response never exposes credentials ───────────────────
class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        return None


def test_health_postgres_never_exposes_credentials(monkeypatch):
    import app.database as db
    cred_url = "postgresql+asyncpg://admin:supersecret@db.internal:5432/shahdol"
    monkeypatch.setattr(db.settings, "database_url", cred_url)
    monkeypatch.setattr(db, "AsyncSessionLocal", lambda: _FakeSession())
    import asyncio
    result = asyncio.run(db.check_db_health())
    assert result["status"] == "healthy"
    assert result["database"] == "postgresql"
    blob = str(result)
    assert "supersecret" not in blob
    assert "admin" not in blob
    assert "db.internal" not in blob
    assert "://" not in blob


def test_health_sqlite_exposes_only_path(monkeypatch):
    import app.database as db
    monkeypatch.setattr(db.settings, "database_url", "sqlite+aiosqlite:///./local.db")
    monkeypatch.setattr(db, "AsyncSessionLocal", lambda: _FakeSession())
    import asyncio
    result = asyncio.run(db.check_db_health())
    assert result["status"] == "healthy"
    assert result["database"] == "sqlite"
    assert "local.db" in str(result)
    assert "://" not in result["path"]
