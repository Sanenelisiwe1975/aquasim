"""Async SQLAlchemy engine + session factory.

Schema management
-----------------
`init_db()` runs Alembic migrations to head on every startup, which is safe
and idempotent.  If Alembic cannot run (e.g., the DB lacks the alembic_version
table from a pre-migration environment), it falls back to SQLAlchemy create_all
so the engine never fails to start because of a schema issue.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import structlog

from engine.core.config import settings
from engine.db.models import Base

log = structlog.get_logger(__name__)

_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

_SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)

import os

# MIGRATIONS_DIR env var lets the container override the default relative path.
# Default (local dev): project-root/migrations — three levels up from engine/db/.
# Docker: set MIGRATIONS_DIR=/app/migrations, since engine code lands at /app/.
_MIGRATIONS_DIR = Path(
    os.getenv("MIGRATIONS_DIR", str(Path(__file__).parent.parent.parent / "migrations"))
)
_ALEMBIC_INI = _MIGRATIONS_DIR / "alembic.ini"


async def init_db() -> None:
    """Run Alembic migrations to head; fall back to create_all on failure."""
    from alembic.config import Config
    from alembic import command as alembic_command

    def _run_migrations() -> None:
        cfg = Config(str(_ALEMBIC_INI))
        # Ensure the engine URL from settings takes precedence over alembic.ini
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        alembic_command.upgrade(cfg, "head")

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _run_migrations)
        log.info("database_migrations_applied")
    except Exception as e:
        log.warning("alembic_migration_failed_falling_back", error=str(e))
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("database_tables_created_via_create_all")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
