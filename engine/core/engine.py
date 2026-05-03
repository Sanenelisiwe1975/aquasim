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
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from engine.backtest import compute_backtest_metrics
from engine.core.config import settings
from engine.core.event_bus import bus, EVT_TICK, EVT_TRADE, EVT_ORDER_NEW, EVT_POSITION_UPDATE
from engine.data.simulator import MarketDataSimulator
from engine.data.backtest_loader import BacktestLoader
from engine.db import init_db, get_session
from engine.db.models import BacktestRun, TradeRecord, OrderRecord
from engine.execution import ExecutionSimulator, LatencyConfig
from engine.kafka import KafkaProducer, KafkaConsumer
from engine.kafka import topics
from engine.models import Order, OrderSide, OrderStatus, OrderType, Tick, Trade
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
            cancel_callback=self._on_order_cancelled,
            latency_config=LatencyConfig(
                base_us=settings.base_latency_us,
                jitter_us=settings.latency_jitter_us,
            ),
        )

        self._strategies: Dict[str, BaseStrategy] = {}
        self._active_orders: Dict[str, Order] = {}
        # throttle equity-curve Redis pushes to 1/sec per strategy
        self._last_equity_push: Dict[str, Optional[datetime]] = {}

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

        # Start all strategies and restore saved risk state
        for strategy in self._strategies.values():
            await strategy.start()
            await self._redis.register_strategy(strategy.strategy_id)
            self._risk.register_strategy(strategy.strategy_id)
            saved_risk = await self._redis.get_risk(strategy.strategy_id)
            if saved_risk:
                self._risk.restore_state(strategy.strategy_id, saved_risk)

        log.info("aquasim_engine_running", strategies=list(self._strategies.keys()), mode=settings.mode)

        # Infrastructure tasks run in both modes
        infra_tasks = [
            asyncio.create_task(self._consumer.run(), name="kafka-consumer"),
            asyncio.create_task(self._exec_sim.run(), name="exec-simulator"),
            asyncio.create_task(self._listen_commands(), name="cmd-listener"),
        ]

        try:
            if settings.mode == "live":
                market_sim = MarketDataSimulator(SYMBOLS, self._producer, self._redis, self._books)
                infra_tasks.append(asyncio.create_task(market_sim.run(), name="market-data-sim"))
                await asyncio.gather(*infra_tasks)
            else:
                await self._run_backtest(infra_tasks)
        except asyncio.CancelledError:
            log.info("engine_shutdown_requested")
        finally:
            await self._shutdown()

    async def _run_backtest(self, infra_tasks: list) -> None:
        """Run backtest replay, persist results, then cancel infrastructure."""
        run_id_prefix = str(uuid.uuid4())
        loader = BacktestLoader(self._producer, self._redis, self._books)

        # Replay ticks to completion; infra tasks consume concurrently
        first_ts, last_ts = await loader.run()

        # Allow exec simulator to drain any in-flight orders
        await asyncio.sleep(2.0)

        if first_ts and last_ts:
            await self._finalize_backtest_runs(run_id_prefix, first_ts, last_ts)

        for task in infra_tasks:
            task.cancel()
        await asyncio.gather(*infra_tasks, return_exceptions=True)

    async def _listen_commands(self) -> None:
        """Subscribe to engine_commands Redis channel published by the API."""
        import json
        import aioredis

        redis = await aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
        pubsub = redis.pubsub()
        await pubsub.subscribe("engine_commands")
        log.info("engine_commands_subscribed")

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    command = json.loads(message["data"])
                    await self._dispatch_command(command)
                except Exception as e:
                    log.error("command_dispatch_error", error=str(e))
        finally:
            await redis.close()

    async def _dispatch_command(self, command: dict) -> None:
        import json
        cmd_type = command.get("type")

        if cmd_type == "submit_order":
            raw = command.get("order", {})
            try:
                order = Order(
                    id=raw["id"],
                    strategy_id=raw["strategy_id"],
                    symbol=raw["symbol"],
                    side=OrderSide(raw["side"]),
                    quantity=float(raw["quantity"]),
                    order_type=OrderType(raw.get("order_type", "MARKET")),
                    limit_price=raw.get("limit_price"),
                    created_at=datetime.fromisoformat(raw["created_at"]),
                )
                await self._on_order(order)
                log.info("manual_order_received", order_id=order.id, symbol=order.symbol)
            except (KeyError, ValueError) as e:
                log.error("submit_order_command_invalid", error=str(e))

        elif cmd_type == "pause_strategy":
            strategy = self._strategies.get(command.get("strategy_id", ""))
            if strategy:
                await strategy.pause()

        elif cmd_type == "resume_strategy":
            strategy = self._strategies.get(command.get("strategy_id", ""))
            if strategy:
                await strategy.resume()

        elif cmd_type == "update_risk":
            strategy_id = command.get("strategy_id", "")
            limits = command.get("limits", {})
            if strategy_id and limits:
                self._risk.apply_overrides(strategy_id, limits)

        else:
            log.warning("unknown_command_type", cmd_type=cmd_type)

    async def _finalize_backtest_runs(
        self,
        run_id_prefix: str,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Create a BacktestRun record per strategy with computed metrics."""
        from sqlalchemy import select, func

        for strategy_id in self._strategies:
            equity = self._pnl.equity_curve(strategy_id)
            metrics = compute_backtest_metrics(equity)

            try:
                async with get_session() as session:
                    result = await session.execute(
                        select(func.count(TradeRecord.id)).where(
                            TradeRecord.strategy_id == strategy_id,
                            TradeRecord.timestamp >= start_time,
                            TradeRecord.timestamp <= end_time,
                        )
                    )
                    trade_count = result.scalar() or 0

                    run = BacktestRun(
                        id=f"{run_id_prefix}_{strategy_id}",
                        strategy_id=strategy_id,
                        symbol=",".join(SYMBOLS),
                        start_time=start_time,
                        end_time=end_time,
                        total_trades=trade_count,
                        realized_pnl=metrics["realized_pnl"],
                        max_drawdown=metrics["max_drawdown"],
                        sharpe_ratio=metrics["sharpe_ratio"],
                        win_rate=metrics["win_rate"],
                        completed=True,
                    )
                    session.add(run)
                    log.info(
                        "backtest_run_saved",
                        strategy_id=strategy_id,
                        trades=trade_count,
                        realized_pnl=round(metrics["realized_pnl"], 2),
                        sharpe=metrics["sharpe_ratio"],
                        win_rate=metrics["win_rate"],
                        max_drawdown=round(metrics["max_drawdown"], 2),
                    )
            except Exception as e:
                log.error("backtest_run_persist_failed", strategy_id=strategy_id, error=str(e))

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
            tick = Tick.from_dict(tick_dict)
        except (KeyError, ValueError) as e:
            log.error("bad_tick_message", error=str(e), keys=list(tick_dict.keys()))
            return

        # Mark all open positions to market
        updated_positions = self._pnl.mark_to_market(tick)

        # Group by strategy so we can do one equity push per strategy
        by_strategy: Dict[str, List] = {}
        for pos in updated_positions:
            self._risk.update_position(pos.strategy_id, pos)
            await self._redis.set_position(pos.strategy_id, pos.symbol, pos.to_dict())
            await self._redis.publish(f"positions:{pos.strategy_id}", pos.to_dict())
            by_strategy.setdefault(pos.strategy_id, []).append(pos)

        # Push one equity point per strategy, throttled to 1/sec, summed across symbols
        for strategy_id, positions in by_strategy.items():
            last_push = self._last_equity_push.get(strategy_id)
            elapsed = (tick.timestamp - last_push).total_seconds() if last_push else None
            if elapsed is None or elapsed >= 1.0:
                total_pnl = round(sum(p.total_pnl for p in positions), 4)
                await self._redis.push_equity_point(strategy_id, {
                    "timestamp": tick.timestamp.isoformat(),
                    "total_pnl": total_pnl,
                })
                self._last_equity_push[strategy_id] = tick.timestamp

        # Re-check queued limit orders now that the book has been updated
        await self._exec_sim.try_fill_pending(tick.symbol)

        # Dispatch tick to strategies concurrently
        await asyncio.gather(
            *[s.on_tick(tick) for s in self._strategies.values()],
            return_exceptions=True,
        )

    async def _on_order_cancelled(self, order: Order) -> None:
        """Called by ExecutionSimulator when a queued limit order expires."""
        strategy = self._strategies.get(order.strategy_id)
        if strategy:
            await strategy.on_reject(order)
        await self._persist_order(order)
        await self._redis.publish("risk_events", {
            "type": "limit_order_expired",
            "order": order.to_dict(),
            "reason": order.rejection_reason,
        })

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

        # Capture pre-fill realized PnL so we can compute the delta for this trade
        pre_pos = self._pnl.get_or_create(trade.strategy_id, trade.symbol)
        prev_realized = pre_pos.realized_pnl

        pos = self._pnl.on_trade(trade)
        trade_pnl = round(pos.realized_pnl - prev_realized, 4)

        # Attach per-trade PnL to the trade record before persisting
        trade.realized_pnl = trade_pnl

        self._risk.update_position(trade.strategy_id, pos)
        # Pass the DELTA, not the cumulative total (bug fix: was pos.realized_pnl)
        self._risk.record_trade_pnl(trade.strategy_id, trade_pnl)

        # Persist to Postgres and sync to Redis
        # _persist_order upserts the order record with FILLED status + fill details
        persist_tasks = [self._persist_trade(trade)]
        if order:
            persist_tasks.append(self._persist_order(order))

        await asyncio.gather(
            *persist_tasks,
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
                    realized_pnl=trade.realized_pnl,
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
