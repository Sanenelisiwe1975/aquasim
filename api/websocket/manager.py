"""
WebSocket Connection Manager
-----------------------------
Manages active WebSocket connections and fans out messages to all subscribers.
Subscribes to Redis pub/sub channels and forwards messages in real-time.
"""
from __future__ import annotations
import asyncio
import json
from typing import Dict, List, Set

import aioredis
from fastapi import WebSocket
import structlog

log = structlog.get_logger(__name__)

# Redis pub/sub channels the API bridges to the browser
CHANNELS = [
    "trades",
    "positions:momentum_v1",
    "positions:mean_rev_v1",
    "risk_events",
]


class ConnectionManager:
    def __init__(self) -> None:
        # channel → set of active WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {c: set() for c in CHANNELS}
        self._all: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket, channel: str = "all") -> None:
        await ws.accept()
        self._all.add(ws)
        if channel != "all" and channel in self._connections:
            self._connections[channel].add(ws)
        log.info("ws_connected", channel=channel, total=len(self._all))

    def disconnect(self, ws: WebSocket, channel: str = "all") -> None:
        self._all.discard(ws)
        for subs in self._connections.values():
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

    async def broadcast_to_channel(self, channel: str, message: dict) -> None:
        subs = self._connections.get(channel, set())
        if not subs:
            return
        data = json.dumps(message)
        dead: List[WebSocket] = []
        for ws in list(subs):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    async def start_redis_listener(self, redis_url: str) -> None:
        """
        Subscribe to Redis pub/sub and forward messages to WebSocket clients.
        Runs as a background task.
        """
        redis = await aioredis.from_url(redis_url, decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(*CHANNELS)
        log.info("redis_pubsub_subscribed", channels=CHANNELS)

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            channel = message["channel"]
            try:
                payload = json.loads(message["data"])
                payload["_channel"] = channel
                await self.broadcast(payload)
            except Exception as e:
                log.error("pubsub_dispatch_error", error=str(e))


manager = ConnectionManager()
