"""
WebSocket Connection Manager
-----------------------------
Manages active WebSocket connections and fans out messages to all subscribers.
Subscribes to Redis pub/sub channels and forwards messages in real-time.

Specific channel subscriptions:
  trades        — every fill event
  risk_events   — order rejections and risk breaches

Pattern subscriptions (psubscribe):
  positions:*   — per-strategy position updates (any strategy)
  orderbook:*   — per-symbol order book snapshots (any symbol)
  ticks:*       — per-symbol price ticks (any symbol)
"""
from __future__ import annotations
import asyncio
import json
from typing import Dict, List, Set

import aioredis
from fastapi import WebSocket
import structlog

log = structlog.get_logger(__name__)

# Exact Redis channels to subscribe to
_CHANNELS = ["trades", "risk_events"]

# Redis pub/sub patterns — matches any channel with these prefixes
_PATTERNS = ["positions:*", "orderbook:*", "ticks:*", "risk:*"]


class ConnectionManager:
    def __init__(self) -> None:
        self._all: Set[WebSocket] = set()
        # channel → set of clients that subscribed via /ws/{channel}
        self._channel_subs: Dict[str, Set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, channel: str = "all") -> None:
        await ws.accept()
        self._all.add(ws)
        if channel != "all":
            self._channel_subs.setdefault(channel, set()).add(ws)
        log.info("ws_connected", channel=channel, total=len(self._all))

    def disconnect(self, ws: WebSocket, channel: str = "all") -> None:
        self._all.discard(ws)
        for subs in self._channel_subs.values():
            subs.discard(ws)
        log.info("ws_disconnected", total=len(self._all))

    async def broadcast(self, message: dict) -> None:
        """Send to every connected client."""
        if not self._all:
            return
        data = json.dumps(message)
        dead: List[WebSocket] = []
        for ws in list(self._all):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def start_redis_listener(self, redis_url: str) -> None:
        """
        Subscribe to Redis pub/sub channels and patterns; forward every
        message to all connected WebSocket clients with a `_channel` field.
        Runs as a background task.
        """
        redis = await aioredis.from_url(redis_url, decode_responses=True)
        pubsub = redis.pubsub()

        await pubsub.subscribe(*_CHANNELS)
        await pubsub.psubscribe(*_PATTERNS)

        log.info("redis_pubsub_subscribed", channels=_CHANNELS, patterns=_PATTERNS)

        async for message in pubsub.listen():
            # Both "message" (exact) and "pmessage" (pattern) carry data
            if message["type"] not in ("message", "pmessage"):
                continue
            try:
                channel = message["channel"]   # actual channel, not the pattern
                payload = json.loads(message["data"])
                payload["_channel"] = channel
                await self.broadcast(payload)
            except Exception as e:
                log.error("pubsub_dispatch_error", error=str(e))


manager = ConnectionManager()
