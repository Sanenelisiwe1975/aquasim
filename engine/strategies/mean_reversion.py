"""
Mean Reversion Strategy
-----------------------
Uses a Bollinger Band approach:
  - Price > upper band → sell (expect reversion down)
  - Price < lower band → buy  (expect reversion up)
  - Price returns to mid band → flatten position
"""
from __future__ import annotations
import math
from collections import deque
from typing import Callable, Coroutine, Deque, List

from engine.models import Tick
from engine.strategies.base import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    def __init__(
        self,
        strategy_id: str,
        symbols: List[str],
        order_callback: Callable[..., Coroutine],
        window: int = 20,
        num_std: float = 2.0,
        trade_qty: float = 100.0,
    ) -> None:
        super().__init__(strategy_id, symbols, order_callback)
        self.window = window
        self.num_std = num_std
        self.trade_qty = trade_qty
        self._prices: dict[str, Deque[float]] = {s: deque(maxlen=window) for s in symbols}
        self._position: dict[str, float] = {s: 0.0 for s in symbols}

    async def on_tick(self, tick: Tick) -> None:
        if tick.symbol not in self._prices:
            return

        self._prices[tick.symbol].append(tick.mid())
        prices = list(self._prices[tick.symbol])

        if len(prices) < self.window:
            return

        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std = math.sqrt(variance)

        upper = mean + self.num_std * std
        lower = mean - self.num_std * std
        mid = tick.mid()
        current_pos = self._position[tick.symbol]

        if mid > upper and current_pos >= 0:
            # Overbought — sell/short (double qty if reversing from long to net-short in one order)
            qty = self.trade_qty * (2 if current_pos > 0 else 1)
            await self.sell(tick.symbol, qty)
            self._position[tick.symbol] = -1.0
            self.log.info("mean_rev_signal", signal="SELL", symbol=tick.symbol,
                          qty=qty, mid=round(mid, 4), upper=round(upper, 4))

        elif mid < lower and current_pos <= 0:
            # Oversold — buy/long (double qty if reversing from short to net-long in one order)
            qty = self.trade_qty * (2 if current_pos < 0 else 1)
            await self.buy(tick.symbol, qty)
            self._position[tick.symbol] = 1.0
            self.log.info("mean_rev_signal", signal="BUY", symbol=tick.symbol,
                          qty=qty, mid=round(mid, 4), lower=round(lower, 4))

        elif lower <= mid <= upper and current_pos != 0:
            # Reverted to mean — flatten
            if current_pos > 0:
                await self.sell(tick.symbol, self.trade_qty)
            else:
                await self.buy(tick.symbol, self.trade_qty)
            self._position[tick.symbol] = 0.0
            self.log.info("mean_rev_signal", signal="FLAT", symbol=tick.symbol)

    async def on_fill(self, order) -> None:
        self.log.info("fill", order_id=order.id, side=order.side.value,
                      qty=order.filled_quantity, price=order.filled_price)
