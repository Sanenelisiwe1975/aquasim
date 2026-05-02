"""Async SQLAlchemy engine + session factory."""
from __future__ import annotations
from contextlib import asynccontextmanager
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


async def init_db() -> None:
    """Create all tables (idempotent — safe to call on every startup)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("database_tables_created")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
