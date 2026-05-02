"""
Redis client wrapper.
Provides typed helpers for the key namespaces used by AquaSim.

Key schema:
  orderbook:{symbol}               → JSON string (order book snapshot)
  position:{strategy_id}:{symbol}  → JSON string (position snapshot)
  pnl:{strategy_id}                → JSON string (PnL summary)
  risk:{strategy_id}               → JSON string (risk summary)
  equity_curve:{strategy_id}       → Redis list of JSON points (capped at 5000)
  ticks:{symbol}                   → Redis list of JSON ticks (capped at 500)
  strategies                       → Redis set of active strategy IDs
"""
from __future__ import annotations
import json
from typing import Any, List, Optional

import aioredis
import structlog

from engine.core.config import settings

log = structlog.get_logger(__name__)

_EQUITY_CURVE_MAX = 5_000
_TICK_HISTORY_MAX = 500


class RedisClient:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        await self._redis.ping()
        log.info("redis_connected", url=settings.redis_url)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    # ── Order Book ───────────────────────────────────────────────────────────

    async def set_orderbook(self, symbol: str, payload: str) -> None:
        await self._redis.set(f"orderbook:{symbol}", payload)

    async def get_orderbook(self, symbol: str) -> Optional[dict]:
        raw = await self._redis.get(f"orderbook:{symbol}")
        return json.loads(raw) if raw else None

    # ── Ticks ────────────────────────────────────────────────────────────────

    async def push_tick(self, symbol: str, tick_dict: dict) -> None:
        key = f"ticks:{symbol}"
        await self._redis.lpush(key, json.dumps(tick_dict))
        await self._redis.ltrim(key, 0, _TICK_HISTORY_MAX - 1)

    async def get_ticks(self, symbol: str, n: int = 100) -> List[dict]:
        key = f"ticks:{symbol}"
        raw_list = await self._redis.lrange(key, 0, n - 1)
        return [json.loads(r) for r in raw_list]

    # ── Positions ────────────────────────────────────────────────────────────

    async def set_position(self, strategy_id: str, symbol: str, payload: dict) -> None:
        await self._redis.set(f"position:{strategy_id}:{symbol}", json.dumps(payload))

    async def get_position(self, strategy_id: str, symbol: str) -> Optional[dict]:
        raw = await self._redis.get(f"position:{strategy_id}:{symbol}")
        return json.loads(raw) if raw else None

    async def get_all_positions(self, strategy_id: str) -> List[dict]:
        keys = await self._redis.keys(f"position:{strategy_id}:*")
        if not keys:
            return []
        values = await self._redis.mget(*keys)
        return [json.loads(v) for v in values if v]

    # ── PnL / Equity Curve ───────────────────────────────────────────────────

    async def set_pnl(self, strategy_id: str, payload: dict) -> None:
        await self._redis.set(f"pnl:{strategy_id}", json.dumps(payload))

    async def get_pnl(self, strategy_id: str) -> Optional[dict]:
        raw = await self._redis.get(f"pnl:{strategy_id}")
        return json.loads(raw) if raw else None

    async def push_equity_point(self, strategy_id: str, point: dict) -> None:
        key = f"equity_curve:{strategy_id}"
        await self._redis.rpush(key, json.dumps(point))
        await self._redis.ltrim(key, -_EQUITY_CURVE_MAX, -1)

    async def get_equity_curve(self, strategy_id: str, n: int = 500) -> List[dict]:
        key = f"equity_curve:{strategy_id}"
        raw_list = await self._redis.lrange(key, -n, -1)
        return [json.loads(r) for r in raw_list]

    # ── Risk ─────────────────────────────────────────────────────────────────

    async def set_risk(self, strategy_id: str, payload: dict) -> None:
        await self._redis.set(f"risk:{strategy_id}", json.dumps(payload))

    async def get_risk(self, strategy_id: str) -> Optional[dict]:
        raw = await self._redis.get(f"risk:{strategy_id}")
        return json.loads(raw) if raw else None

    # ── Strategy Registry ────────────────────────────────────────────────────

    async def register_strategy(self, strategy_id: str) -> None:
        await self._redis.sadd("strategies", strategy_id)

    async def get_strategy_ids(self) -> List[str]:
        return list(await self._redis.smembers("strategies"))

    # ── Pub/Sub (for API WebSocket fan-out) ──────────────────────────────────

    async def publish(self, channel: str, message: dict) -> None:
        await self._redis.publish(channel, json.dumps(message))

    # ── Generic ──────────────────────────────────────────────────────────────

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        await self._redis.set(key, json.dumps(value), ex=ex)

    async def get(self, key: str) -> Any:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw else None
