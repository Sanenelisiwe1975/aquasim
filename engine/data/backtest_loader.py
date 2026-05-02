"""
Backtest Data Loader
--------------------
Reads historical tick data from a CSV file and replays it to Kafka at
configurable speed (backtest_speed_multiplier × real-time).

CSV format expected:
  timestamp,symbol,price,bid,ask,bid_size,ask_size,volume
"""
from __future__ import annotations
import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import List

import structlog

from engine.core.config import settings
from engine.kafka import KafkaProducer
from engine.kafka.topics import MARKET_TICKS
from engine.models import Tick
from engine.orderbook import OrderBook
from engine.redis_client import RedisClient

log = structlog.get_logger(__name__)


class BacktestLoader:
    def __init__(
        self,
        producer: KafkaProducer,
        redis: RedisClient,
        order_books: dict[str, OrderBook],
    ) -> None:
        self._producer = producer
        self._redis = redis
        self._books = order_books

    async def run(self, filepath: str | None = None) -> None:
        path = Path(filepath or settings.backtest_file)
        if not path.exists():
            log.error("backtest_file_not_found", path=str(path))
            return

        ticks = self._load_csv(path)
        if not ticks:
            log.error("no_ticks_loaded")
            return

        log.info("backtest_replay_starting", ticks=len(ticks), file=str(path),
                 speed=settings.backtest_speed_multiplier)

        prev_ts: datetime | None = None
        sequence = 0

        for tick in ticks:
            if prev_ts is not None:
                gap_s = (tick.timestamp - prev_ts).total_seconds()
                sleep_s = gap_s / settings.backtest_speed_multiplier
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)

            tick.sequence = sequence
            sequence += 1
            tick_dict = tick.to_dict()

            await self._producer.send(MARKET_TICKS, tick_dict, key=tick.symbol)

            book = self._books.get(tick.symbol)
            if book:
                book.update_from_tick(tick.bid, tick.ask, tick.bid_size, tick.ask_size, tick.price)
                await self._redis.set_orderbook(tick.symbol, book.to_redis_payload())
                await self._redis.push_tick(tick.symbol, tick_dict)

            prev_ts = tick.timestamp

        log.info("backtest_replay_complete", ticks=sequence)

    @staticmethod
    def _load_csv(path: Path) -> List[Tick]:
        ticks: List[Tick] = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ticks.append(
                        Tick(
                            symbol=row["symbol"],
                            price=float(row["price"]),
                            bid=float(row["bid"]),
                            ask=float(row["ask"]),
                            bid_size=float(row.get("bid_size", 100)),
                            ask_size=float(row.get("ask_size", 100)),
                            volume=float(row.get("volume", 0)),
                            timestamp=datetime.fromisoformat(row["timestamp"]),
                        )
                    )
                except (KeyError, ValueError) as e:
                    log.warning("bad_csv_row", error=str(e), row=row)
        return ticks
