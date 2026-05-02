"""
Execution Simulator
-------------------
Receives orders from strategies (post risk-check), applies simulated latency,
then matches against the current order book to produce Trade fills.

Slippage model:
  - MARKET orders walk the book; large orders incur price impact.
  - LIMIT orders fill if the market crosses the limit price.
"""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Callable, Coroutine, Dict

import structlog

from engine.execution.latency import LatencySimulator, LatencyConfig
from engine.models import Order, OrderSide, OrderStatus, OrderType, Trade
from engine.orderbook import OrderBook

log = structlog.get_logger(__name__)


class ExecutionSimulator:
    def __init__(
        self,
        order_books: Dict[str, OrderBook],
        trade_callback: Callable[[Trade], Coroutine],
        latency_config: LatencyConfig | None = None,
    ) -> None:
        self._books = order_books
        self._on_trade = trade_callback
        self._latency = LatencySimulator(latency_config)
        self._pending: asyncio.Queue[Order] = asyncio.Queue()

    async def submit(self, order: Order) -> None:
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = datetime.utcnow()
        await self._pending.put(order)

    async def run(self) -> None:
        """Background loop — pulls orders and processes them with latency."""
        log.info("execution_simulator_started")
        while True:
            order = await self._pending.get()
            # Fire-and-forget so concurrent orders are processed independently.
            asyncio.create_task(self._process(order))

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
        qty = order.quantity

        avg_price = book.simulate_market_impact(side, qty)
        mid = book.mid_price() or avg_price
        slippage = abs(avg_price - mid)

        order.filled_price = avg_price
        order.filled_quantity = qty
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.utcnow()

        trade = Trade(
            order_id=order.id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=side,
            quantity=qty,
            price=avg_price,
            timestamp=datetime.utcnow(),
            latency_us=latency_us,
            slippage=slippage,
        )
        await self._on_trade(trade)
        log.info("market_fill", order_id=order.id, price=round(avg_price, 4),
                 qty=qty, latency_us=latency_us, slippage=round(slippage, 6))

    async def _fill_limit(self, order: Order, book: OrderBook, latency_us: int) -> None:
        best_bid = book.best_bid()
        best_ask = book.best_ask()

        can_fill = (
            (order.side == OrderSide.BUY and best_ask and best_ask[0] <= order.limit_price)
            or (order.side == OrderSide.SELL and best_bid and best_bid[0] >= order.limit_price)
        )

        if not can_fill:
            # In a real system we'd queue this; here we reject for simplicity.
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "Limit price not available in book"
            log.info("limit_not_filled", order_id=order.id, limit=order.limit_price)
            return

        fill_price = order.limit_price
        order.filled_price = fill_price
        order.filled_quantity = order.quantity
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.utcnow()

        trade = Trade(
            order_id=order.id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=fill_price,
            timestamp=datetime.utcnow(),
            latency_us=latency_us,
            slippage=0.0,
        )
        await self._on_trade(trade)
        log.info("limit_fill", order_id=order.id, price=fill_price, qty=order.quantity)
