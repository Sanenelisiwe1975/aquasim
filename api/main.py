"""
AquaSim FastAPI Application
----------------------------
REST endpoints + WebSocket live feed.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import aioredis
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers import orderbook, orders, positions, trades, strategies, backtest
from api.websocket.manager import manager

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(os.getenv("LOG_LEVEL", "INFO"))
    ),
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger("api")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aquasim:aquasim_secret@localhost:5432/aquasim",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = await aioredis.from_url(
        REDIS_URL, encoding="utf-8", decode_responses=True, max_connections=20
    )
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
    app.state.db_session = async_sessionmaker(engine, expire_on_commit=False)

    # Background Redis pub/sub → WebSocket fan-out
    listener_task = asyncio.create_task(
        manager.start_redis_listener(REDIS_URL), name="redis-pubsub"
    )
    log.info("api_started")

    yield

    # Shutdown
    listener_task.cancel()
    await app.state.redis.close()
    await engine.dispose()
    log.info("api_stopped")


app = FastAPI(
    title="AquaSim API",
    description="Low-Latency Event-Driven Trading Simulation Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(orderbook.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(trades.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    All-topics live feed.
    The client receives JSON messages with a `_channel` field indicating the source.
    """
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; client can send pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.websocket("/ws/{channel}")
async def websocket_channel(ws: WebSocket, channel: str):
    await manager.connect(ws, channel)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, channel)
