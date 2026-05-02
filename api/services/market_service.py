"""Shared service layer — wraps Redis + DB reads used by multiple routers."""
from __future__ import annotations
from typing import Any, Dict, List, Optional

import aioredis
import structlog

log = structlog.get_logger(__name__)


class MarketService:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def get_orderbook(self, symbol: str) -> Optional[dict]:
        import json
        raw = await self._redis.get(f"orderbook:{symbol}")
        return json.loads(raw) if raw else None

    async def get_ticks(self, symbol: str, n: int = 100) -> List[dict]:
        import json
        raw_list = await self._redis.lrange(f"ticks:{symbol}", 0, n - 1)
        return [json.loads(r) for r in raw_list]

    async def get_positions(self, strategy_id: str) -> List[dict]:
        import json
        keys = await self._redis.keys(f"position:{strategy_id}:*")
        if not keys:
            return []
        values = await self._redis.mget(*keys)
        return [json.loads(v) for v in values if v]

    async def get_all_positions(self) -> Dict[str, List[dict]]:
        import json
        keys = await self._redis.keys("position:*")
        result: Dict[str, List[dict]] = {}
        for key in keys:
            raw = await self._redis.get(key)
            if raw:
                parts = key.split(":")   # position:{strategy_id}:{symbol}
                if len(parts) == 3:
                    sid = parts[1]
                    if sid not in result:
                        result[sid] = []
                    result[sid].append(json.loads(raw))
        return result

    async def get_equity_curve(self, strategy_id: str, n: int = 500) -> List[dict]:
        import json
        raw_list = await self._redis.lrange(f"equity_curve:{strategy_id}", -n, -1)
        return [json.loads(r) for r in raw_list]

    async def get_risk(self, strategy_id: str) -> Optional[dict]:
        import json
        raw = await self._redis.get(f"risk:{strategy_id}")
        return json.loads(raw) if raw else None

    async def get_strategy_ids(self) -> List[str]:
        return list(await self._redis.smembers("strategies"))
