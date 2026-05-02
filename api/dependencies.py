"""FastAPI dependency injection — Redis, DB session, service layer."""
from __future__ import annotations
from typing import AsyncGenerator

import aioredis
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import MarketService


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.db_session() as session:
        yield session


def get_market_service(request: Request) -> MarketService:
    return MarketService(request.app.state.redis)
