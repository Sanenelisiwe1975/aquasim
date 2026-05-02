"""
Market Data Simulator
---------------------
Generates realistic synthetic tick data using a geometric Brownian motion
price process with configurable drift, volatility, and spread.

Publishes to Kafka `market_ticks` and `orderbook_updates` topics.
Also maintains an in-process OrderBook and syncs it to Redis.
"""
from __future__ import annotations
import asyncio
import math
import random
from datetime import datetime
from typing import Dict, List

import numpy as np
import structlog

from engine.core.config import settings
from engine.kafka import KafkaProducer
from engine.kafka.topics import MARKET_TICKS, ORDERBOOK_UPDATES
from engine.models import Tick
from engine.orderbook import OrderBook
from engine.redis_client import RedisClient

log = structlog.get_logger(__name__)


class MarketDataSimulator:
    def __init__(
        self,
        symbols: List[str],
        producer: KafkaProducer,
        redis: RedisClient,
        order_books: Dict[str, OrderBook],
    ) -> None:
        self._symbols = symbols
        self._producer = producer
        self._redis = redis
        self._books = order_books
        # Per-symbol state
        self._prices: Dict[str, float] = {s: settings.initial_price for s in symbols}
        self._sequence: Dict[str, int] = {s: 0 for s in symbols}
        self._vol = settings.price_volatility
        self._spread_bps = settings.spread_bps
        self._levels = settings.orderbook_levels

    async def run(self) -> None:
        log.info("market_data_simulator_started", symbols=self._symbols,
                 interval_ms=settings.tick_interval_ms)
        while True:
            for symbol in self._symbols:
                tick = self._generate_tick(symbol)
                await self._publish_tick(tick)
            await asyncio.sleep(settings.tick_interval_ms / 1000.0)

    def _generate_tick(self, symbol: str) -> Tick:
        """GBM price step + synthetic order book levels."""
        prev_price = self._prices[symbol]
        # Geometric Brownian Motion step
        dt = settings.tick_interval_ms / 1000.0
        drift = 0.0   # zero drift for the sim; strategies work against noise
        shock = random.gauss(0, 1)
        new_price = prev_price * math.exp(
            (drift - 0.5 * self._vol ** 2) * dt + self._vol * math.sqrt(dt) * shock
        )
        self._prices[symbol] = new_price

        half_spread = new_price * (self._spread_bps / 10_000) / 2.0
        bid = new_price - half_spread
        ask = new_price + half_spread

        # Randomised top-of-book sizes
        bid_size = round(random.uniform(50, 500), 2)
        ask_size = round(random.uniform(50, 500), 2)
        volume = round(random.uniform(10, 200), 2)

        seq = self._sequence[symbol]
        self._sequence[symbol] = seq + 1

        return Tick(
            symbol=symbol,
            price=round(new_price, 6),
            bid=round(bid, 6),
            ask=round(ask, 6),
            bid_size=bid_size,
            ask_size=ask_size,
            volume=volume,
            timestamp=datetime.utcnow(),
            sequence=seq,
        )

    def _build_book_levels(
        self, symbol: str, bid: float, ask: float
    ) -> list:
        """Generate N synthetic depth levels around the spread."""
        levels = []
        tick_size = self._prices[symbol] * 0.0001  # 1 basis point per level
        for i in range(1, self._levels):
            levels.append((round(bid - i * tick_size, 6), round(random.uniform(100, 1000), 2), "bid"))
            levels.append((round(ask + i * tick_size, 6), round(random.uniform(100, 1000), 2), "ask"))
        return levels

    async def _publish_tick(self, tick: Tick) -> None:
        tick_dict = tick.to_dict()

        # Publish raw tick
        await self._producer.send(MARKET_TICKS, tick_dict, key=tick.symbol)

        # Update in-process order book
        book = self._books.get(tick.symbol)
        if book:
            extra_levels = self._build_book_levels(tick.symbol, tick.bid, tick.ask)
            book.update_from_tick(
                tick.bid, tick.ask, tick.bid_size, tick.ask_size, tick.price, extra_levels
            )
            book_payload = book.to_redis_payload()

            # Sync to Redis
            await self._redis.set_orderbook(tick.symbol, book_payload)
            await self._redis.push_tick(tick.symbol, tick_dict)

            # Publish book snapshot to Kafka
            await self._producer.send(ORDERBOOK_UPDATES, book.to_dict(), key=tick.symbol)

            # Publish to Redis pub/sub so the API WebSocket can push live updates
            await self._redis.publish(f"orderbook:{tick.symbol}", book.to_dict())
            await self._redis.publish(f"ticks:{tick.symbol}", tick_dict)
