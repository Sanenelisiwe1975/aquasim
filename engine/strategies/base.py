"""
BaseStrategy — all strategies inherit from this.

To add a new strategy:
  1. Subclass BaseStrategy
  2. Implement on_tick() (and optionally on_trade(), on_fill())
  3. Register it in engine/core/engine.py

The strategy NEVER touches orders directly; it calls self.submit_order() which
routes through the risk manager and execution simulator.
"""
from __future__ import annotations
import abc
import asyncio
from datetime import datetime
from typing import Callable, Coroutine, List, Optional
import structlog

from engine.models import Order, OrderSide, OrderType, Tick, Trade

log = structlog.get_logger(__name__)


class BaseStrategy(abc.ABC):
    def __init__(
        self,
        strategy_id: str,
        symbols: List[str],
        order_callback: Callable[[Order], Coroutine],
    ) -> None:
        self.strategy_id = strategy_id
        self.symbols = symbols
        self._submit_order = order_callback
        self._running = False
        self._paused = False
        self.log = structlog.get_logger(strategy_id)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        await self.on_start()
        self.log.info("strategy_started", symbols=self.symbols)

    async def stop(self) -> None:
        self._running = False
        await self.on_stop()
        self.log.info("strategy_stopped")

    async def pause(self) -> None:
        self._paused = True
        self.log.info("strategy_paused")

    async def resume(self) -> None:
        self._paused = False
        self.log.info("strategy_resumed")

    # ── Hook methods (override in subclass) ─────────────────────────────────

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass

    @abc.abstractmethod
    async def on_tick(self, tick: Tick) -> None:
        """Called for every market tick on a subscribed symbol."""

    async def on_fill(self, order: Order) -> None:
        """Called when one of this strategy's orders is filled."""
        pass

    async def on_reject(self, order: Order) -> None:
        """Called when an order is rejected by risk or execution."""
        self.log.warning("order_rejected", order_id=order.id, reason=order.rejection_reason)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> Optional[Order]:
        return await self._place(symbol, OrderSide.BUY, quantity, order_type, limit_price)

    async def sell(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> Optional[Order]:
        return await self._place(symbol, OrderSide.SELL, quantity, order_type, limit_price)

    async def _place(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        limit_price: Optional[float],
    ) -> Optional[Order]:
        if not self._running or self._paused:
            return None
        order = Order(
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        await self._submit_order(order)
        return order
