"""
Execution Simulator
-------------------
Receives orders from strategies (post risk-check), applies simulated latency,
then matches against the current order book to produce Trade fills.

Slippage model:
  - MARKET orders walk the book for market impact, then add a small adverse
    price move proportional to the latency window (execution risk).
  - LIMIT orders are queued; they re-check the book on every tick and fill
    when the market crosses the limit.  Unfilled orders expire after
    LIMIT_ORDER_TTL_TICKS ticks (~6 s at 100 ms/tick).
"""
from __future__ import annotations
import asyncio
import math
import random
from datetime import datetime
from typing import Callable, Coroutine, Dict, List, Optional

import structlog

from engine.execution.latency import LatencySimulator, LatencyConfig
from engine.models import Order, OrderSide, OrderStatus, OrderType, Trade
from engine.orderbook import OrderBook

log = structlog.get_logger(__name__)

LIMIT_ORDER_TTL_TICKS = 60     # ticks before a queued limit order expires
_VOL_PER_US = 1e-8             # price std-dev per microsecond (≈0.001% per 100ms tick)


class ExecutionSimulator:
    def __init__(
        self,
        order_books: Dict[str, OrderBook],
        trade_callback: Callable[[Trade], Coroutine],
        cancel_callback: Optional[Callable[[Order], Coroutine]] = None,
        latency_config: LatencyConfig | None = None,
    ) -> None:
        self._books = order_books
        self._on_trade = trade_callback
        self._on_cancel = cancel_callback
        self._latency = LatencySimulator(latency_config)
        self._pending: asyncio.Queue[Order] = asyncio.Queue()
        # symbol → list of queued limit orders
        self._limit_queue: Dict[str, List[Order]] = {}
        # order_id → number of ticks the order has been waiting
        self._order_age: Dict[str, int] = {}

    async def submit(self, order: Order) -> None:
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = datetime.utcnow()
        await self._pending.put(order)

    async def run(self) -> None:
        log.info("execution_simulator_started")
        while True:
            order = await self._pending.get()
            asyncio.create_task(self._process(order))

    async def try_fill_pending(self, symbol: str) -> None:
        """Re-check queued limit orders for `symbol` against the current book.

        Called by the engine after every tick book update.
        Orders that cannot fill are aged; those that exceed TTL are cancelled.
        """
        queue = self._limit_queue.get(symbol)
        if not queue:
            return

        book = self._books.get(symbol)
        if book is None:
            return

        remaining: List[Order] = []
        for order in queue:
            age = self._order_age.get(order.id, 0) + 1
            self._order_age[order.id] = age

            if age > LIMIT_ORDER_TTL_TICKS:
                order.status = OrderStatus.CANCELLED
                order.rejection_reason = f"Limit order expired after {age} ticks"
                self._order_age.pop(order.id, None)
                log.info("limit_order_expired", order_id=order.id, symbol=symbol, age=age)
                if self._on_cancel:
                    asyncio.create_task(self._on_cancel(order))
                continue

            if self._can_fill_limit(order, book):
                self._order_age.pop(order.id, None)
                latency_us = self._latency.sample_us()
                asyncio.create_task(self._fill_limit_queued(order, book, latency_us))
            else:
                remaining.append(order)

        self._limit_queue[symbol] = remaining

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _process(self, order: Order) -> None:
        latency_us = await self._latency.delay()

        book = self._books.get(order.symbol)
        if book is None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"No order book for {order.symbol}"
            log.warning("no_book_for_symbol", symbol=order.symbol)
            return

        if order.order_type == OrderType.MARKET:
            await self._fill_market(order, book, latency_us)
        else:
            await self._fill_limit(order, book, latency_us)

    async def _fill_market(self, order: Order, book: OrderBook, latency_us: int) -> None:
        side = order.side.value
        qty  = order.quantity

        # Walk the book for market impact price
        avg_price = book.simulate_market_impact(side, qty)

        # Reference price: best quoted price on the take side (not mid)
        ref = book.best_ask() if order.side == OrderSide.BUY else book.best_bid()
        ref_price = ref[0] if ref else avg_price

        # Adverse price move during the latency window (execution risk)
        adverse = abs(random.gauss(0, avg_price * _VOL_PER_US * math.sqrt(latency_us)))
        if order.side == OrderSide.BUY:
            fill_price = avg_price + adverse
        else:
            fill_price = avg_price - adverse

        slippage = abs(fill_price - ref_price)
        fill_time = book.updated_at   # simulated time — accurate in backtest

        order.filled_price    = fill_price
        order.filled_quantity = qty
        order.status          = OrderStatus.FILLED
        order.filled_at       = fill_time

        trade = Trade(
            order_id=order.id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=side,
            quantity=qty,
            price=fill_price,
            timestamp=fill_time,
            latency_us=latency_us,
            slippage=slippage,
        )
        await self._on_trade(trade)
        log.info("market_fill", order_id=order.id, price=round(fill_price, 4),
                 qty=qty, latency_us=latency_us, slippage=round(slippage, 6))

    async def _fill_limit(self, order: Order, book: OrderBook, latency_us: int) -> None:
        if self._can_fill_limit(order, book):
            await self._fill_limit_queued(order, book, latency_us)
        else:
            # Queue for later rather than reject immediately
            self._limit_queue.setdefault(order.symbol, []).append(order)
            self._order_age[order.id] = 0
            log.info("limit_order_queued", order_id=order.id,
                     symbol=order.symbol, limit=order.limit_price)

    async def _fill_limit_queued(self, order: Order, book: OrderBook, latency_us: int) -> None:
        fill_price = order.limit_price
        fill_time  = book.updated_at

        order.filled_price    = fill_price
        order.filled_quantity = order.quantity
        order.status          = OrderStatus.FILLED
        order.filled_at       = fill_time

        trade = Trade(
            order_id=order.id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=fill_price,
            timestamp=fill_time,
            latency_us=latency_us,
            slippage=0.0,
        )
        await self._on_trade(trade)
        log.info("limit_fill", order_id=order.id, price=fill_price, qty=order.quantity)

    @staticmethod
    def _can_fill_limit(order: Order, book: OrderBook) -> bool:
        best_bid = book.best_bid()
        best_ask = book.best_ask()
        if order.side == OrderSide.BUY:
            return best_ask is not None and best_ask[0] <= order.limit_price
        return best_bid is not None and best_bid[0] >= order.limit_price
