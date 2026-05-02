"""
AquaSim Core Engine
-------------------
Orchestrates all components:
  1. Starts infrastructure connections (Kafka, Redis, Postgres)
  2. Launches market data producer (live sim or backtest replay)
  3. Wires strategies to the Kafka market_ticks consumer
  4. Routes orders through Risk → Execution → PnL → Redis/Postgres persistence
  5. Publishes state updates back to Kafka and Redis pub/sub for the API layer
"""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Dict, List

import structlog

from engine.core.config import settings
from engine.core.event_bus import bus, EVT_TICK, EVT_TRADE, EVT_ORDER_NEW, EVT_POSITION_UPDATE
from engine.data.simulator import MarketDataSimulator
from engine.data.backtest_loader import BacktestLoader
from engine.db import init_db, get_session
from engine.db.models import TradeRecord, OrderRecord
from engine.execution import ExecutionSimulator, LatencyConfig
from engine.kafka import KafkaProducer, KafkaConsumer
from engine.kafka import topics
from engine.models import Order, OrderStatus, Tick, Trade
from engine.orderbook import OrderBook
from engine.pnl import PnLTracker
from engine.redis_client import RedisClient
from engine.risk import RiskManager
from engine.strategies import MomentumStrategy, MeanReversionStrategy
from engine.strategies.base import BaseStrategy

log = structlog.get_logger(__name__)

SYMBOLS = ["AAPL", "MSFT", "GOOGL"]


class AquaSimEngine:
    def __init__(self) -> None:
        self._producer = KafkaProducer()
        self._consumer = KafkaConsumer(topics=[topics.MARKET_TICKS])
        self._redis = RedisClient()
        self._risk = RiskManager()
        self._pnl = PnLTracker()

        # One order book per symbol, shared across components
        self._books: Dict[str, OrderBook] = {
            s: OrderBook(s, depth=settings.orderbook_levels) for s in SYMBOLS
        }

        self._exec_sim = ExecutionSimulator(
            order_books=self._books,
            trade_callback=self._on_trade,
            latency_config=LatencyConfig(
                base_us=settings.base_latency_us,
                jitter_us=settings.latency_jitter_us,
            ),
        )

        self._strategies: Dict[str, BaseStrategy] = {}
        self._active_orders: Dict[str, Order] = {}

    # ── Public lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        log.info("aquasim_engine_starting", mode=settings.mode)

        # Connect infrastructure
        await self._redis.connect()
        await init_db()
        await self._producer.start()
        await self._consumer.start()

        # Register strategies
        self._register_strategy(
            MomentumStrategy(
                strategy_id="momentum_v1",
                symbols=SYMBOLS,
                order_callback=self._on_order,
                short_window=10,
                long_window=30,
                trade_qty=50.0,
            )
        )
        self._register_strategy(
            MeanReversionStrategy(
                strategy_id="mean_rev_v1",
                symbols=SYMBOLS,
                order_callback=self._on_order,
                window=20,
                num_std=2.0,
                trade_qty=50.0,
            )
        )

        # Wire Kafka consumer → strategy dispatch
        self._consumer.register(topics.MARKET_TICKS, self._dispatch_tick)

        # Start all strategies
        for strategy in self._strategies.values():
            await strategy.start()
            await self._redis.register_strategy(strategy.strategy_id)
            self._risk.register_strategy(strategy.strategy_id)

        # Assemble concurrent tasks
        tasks = [
            asyncio.create_task(self._consumer.run(), name="kafka-consumer"),
            asyncio.create_task(self._exec_sim.run(), name="exec-simulator"),
        ]

        if settings.mode == "live":
            market_sim = MarketDataSimulator(SYMBOLS, self._producer, self._redis, self._books)
            tasks.append(asyncio.create_task(market_sim.run(), name="market-data-sim"))
        else:
            loader = BacktestLoader(self._producer, self._redis, self._books)
            tasks.append(asyncio.create_task(loader.run(), name="backtest-loader"))

        log.info("aquasim_engine_running", strategies=list(self._strategies.keys()), mode=settings.mode)

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("engine_shutdown_requested")
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        for strategy in self._strategies.values():
            await strategy.stop()
        await self._consumer.stop()
        await self._producer.stop()
        await self._redis.close()
        log.info("aquasim_engine_stopped")

    # ── Strategy registration ─────────────────────────────────────────────────

    def _register_strategy(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.strategy_id] = strategy
        log.info("strategy_registered", strategy_id=strategy.strategy_id)

    # ── Event handlers ────────────────────────────────────────────────────────

    async def _dispatch_tick(self, tick_dict: dict) -> None:
        """Deserialise a Kafka tick message and fan-out to all strategies."""
        try:
            from engine.models import Tick
            tick = Tick(
                symbol=tick_dict["symbol"],
                price=tick_dict["price"],
                bid=tick_dict["bid"],
                ask=tick_dict["ask"],
                bid_size=tick_dict["bid_size"],
                ask_size=tick_dict["ask_size"],
                volume=tick_dict["volume"],
                timestamp=datetime.fromisoformat(tick_dict["timestamp"]),
                sequence=tick_dict.get("sequence", 0),
            )
        except (KeyError, ValueError) as e:
            log.error("bad_tick_message", error=str(e))
            return

        # Mark all open positions to market
        updated_positions = self._pnl.mark_to_market(tick)
        for pos in updated_positions:
            self._risk.update_position(pos.strategy_id, pos)
            await self._redis.set_position(pos.strategy_id, pos.symbol, pos.to_dict())
            await self._redis.push_equity_point(pos.strategy_id, {
                "timestamp": tick.timestamp.isoformat(),
                "total_pnl": round(pos.total_pnl, 4),
            })
            await self._redis.publish(
                f"positions:{pos.strategy_id}",
                pos.to_dict(),
            )

        # Dispatch tick to strategies concurrently
        await asyncio.gather(
            *[s.on_tick(tick) for s in self._strategies.values()],
            return_exceptions=True,
        )

    async def _on_order(self, order: Order) -> None:
        """Called by strategies when they want to place an order."""
        # Get current price for risk sizing
        book = self._books.get(order.symbol)
        current_price = book.mid_price() if book else settings.initial_price

        approved, reason = self._risk.check_order(order, current_price or settings.initial_price)
        if not approved:
            strategy = self._strategies.get(order.strategy_id)
            if strategy:
                await strategy.on_reject(order)
            await self._persist_order(order)
            await self._redis.publish("risk_events", {
                "type": "order_rejected",
                "order": order.to_dict(),
                "reason": reason,
            })
            return

        self._active_orders[order.id] = order
        await self._exec_sim.submit(order)
        await self._persist_order(order)
        await self._producer.send(topics.ORDERS, order.to_dict(), key=order.strategy_id)

    async def _on_trade(self, trade: Trade) -> None:
        """Called by ExecutionSimulator when an order is filled."""
        order = self._active_orders.pop(trade.order_id, None)
        if order:
            order.status = OrderStatus.FILLED
            order.filled_price = trade.price
            order.filled_quantity = trade.quantity
            order.filled_at = trade.timestamp

            strategy = self._strategies.get(order.strategy_id)
            if strategy:
                await strategy.on_fill(order)

        # Update PnL
        pos = self._pnl.on_trade(trade)
        self._risk.update_position(trade.strategy_id, pos)
        self._risk.record_trade_pnl(trade.strategy_id, pos.realized_pnl)

        # Persist to Postgres and sync to Redis
        await asyncio.gather(
            self._persist_trade(trade),
            self._redis.set_position(trade.strategy_id, trade.symbol, pos.to_dict()),
            self._redis.set_pnl(trade.strategy_id, {
                "total_realized": pos.realized_pnl,
                "total_unrealized": pos.unrealized_pnl,
            }),
            self._redis.set_risk(
                trade.strategy_id,
                self._risk.get_risk_summary(trade.strategy_id),
            ),
            self._producer.send(topics.TRADES, trade.to_dict(), key=trade.strategy_id),
            self._redis.publish("trades", trade.to_dict()),
            self._redis.publish(f"positions:{trade.strategy_id}", pos.to_dict()),
        )

        log.info(
            "trade_processed",
            trade_id=trade.id,
            strategy=trade.strategy_id,
            symbol=trade.symbol,
            side=trade.side,
            qty=trade.quantity,
            price=round(trade.price, 4),
            realized_pnl=round(pos.realized_pnl, 2),
        )

    # ── Persistence helpers ───────────────────────────────────────────────────

    async def _persist_trade(self, trade: Trade) -> None:
        try:
            async with get_session() as session:
                record = TradeRecord(
                    id=trade.id,
                    order_id=trade.order_id,
                    strategy_id=trade.strategy_id,
                    symbol=trade.symbol,
                    side=trade.side,
                    quantity=trade.quantity,
                    price=trade.price,
                    notional=trade.notional,
                    latency_us=trade.latency_us,
                    slippage=trade.slippage,
                    timestamp=trade.timestamp,
                )
                session.add(record)
        except Exception as e:
            log.error("trade_persist_failed", error=str(e), trade_id=trade.id)

    async def _persist_order(self, order: Order) -> None:
        try:
            async with get_session() as session:
                record = OrderRecord(
                    id=order.id,
                    strategy_id=order.strategy_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=order.quantity,
                    order_type=order.order_type.value,
                    limit_price=order.limit_price,
                    status=order.status.value,
                    filled_price=order.filled_price,
                    filled_quantity=order.filled_quantity,
                    rejection_reason=order.rejection_reason,
                    created_at=order.created_at,
                    submitted_at=order.submitted_at,
                    filled_at=order.filled_at,
                )
                session.merge(record)
        except Exception as e:
            log.error("order_persist_failed", error=str(e), order_id=order.id)
