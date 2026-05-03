"""
Momentum Strategy
-----------------
Buys when the short EMA crosses above the long EMA (golden cross).
Sells / goes short when the short EMA crosses below the long EMA (death cross).
Exits the position on the opposite signal.
"""
from __future__ import annotations
from collections import deque
from typing import Callable, Coroutine, Deque, List, Optional

from engine.models import Tick
from engine.strategies.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    def __init__(
        self,
        strategy_id: str,
        symbols: List[str],
        order_callback: Callable[..., Coroutine],
        short_window: int = 10,
        long_window: int = 30,
        trade_qty: float = 100.0,
    ) -> None:
        super().__init__(strategy_id, symbols, order_callback)
        self.short_window = short_window
        self.long_window = long_window
        self.trade_qty = trade_qty
        # per-symbol price buffer and signal state
        self._prices: dict[str, Deque[float]] = {s: deque(maxlen=long_window) for s in symbols}
        self._position: dict[str, float] = {s: 0.0 for s in symbols}  # +1 long, -1 short, 0 flat

    async def on_tick(self, tick: Tick) -> None:
        if tick.symbol not in self._prices:
            return

        self._prices[tick.symbol].append(tick.mid())
        prices = self._prices[tick.symbol]

        if len(prices) < self.long_window:
            return  # not enough data yet

        short_ema = self._ema(list(prices), self.short_window)
        long_ema = self._ema(list(prices), self.long_window)
        current_pos = self._position[tick.symbol]

        if short_ema > long_ema and current_pos <= 0:
            # Golden cross — go long (double qty if reversing from short to net-long in one order)
            qty = self.trade_qty * (2 if current_pos < 0 else 1)
            await self.buy(tick.symbol, qty)
            self._position[tick.symbol] = 1.0
            self.log.info("momentum_signal", signal="BUY", symbol=tick.symbol,
                          qty=qty, short_ema=round(short_ema, 4), long_ema=round(long_ema, 4))

        elif short_ema < long_ema and current_pos >= 0:
            # Death cross — go short (double qty if reversing from long to net-short in one order)
            qty = self.trade_qty * (2 if current_pos > 0 else 1)
            await self.sell(tick.symbol, qty)
            self._position[tick.symbol] = -1.0
            self.log.info("momentum_signal", signal="SELL", symbol=tick.symbol,
                          qty=qty, short_ema=round(short_ema, 4), long_ema=round(long_ema, 4))

    async def on_fill(self, order) -> None:
        self.log.info("fill", order_id=order.id, side=order.side.value,
                      qty=order.filled_quantity, price=order.filled_price)

    @staticmethod
    def _ema(prices: List[float], window: int) -> float:
        k = 2.0 / (window + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = p * k + ema * (1 - k)
        return ema
