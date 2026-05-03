"""
PnL Tracker
-----------
Maintains per-strategy, per-symbol positions.  On every tick it marks
all open positions to market and samples the strategy-level equity curve
at 1-second intervals (summed across all symbols).
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional
import structlog

from engine.models import Position, Tick, Trade

log = structlog.get_logger(__name__)

_EQUITY_SAMPLE_INTERVAL_S = 1.0   # sample rate for the equity curve
_EQUITY_CURVE_MAX = 10_000        # hard cap on in-memory points


class PnLTracker:
    def __init__(self) -> None:
        # strategy_id → symbol → Position
        self._positions: Dict[str, Dict[str, Position]] = {}
        # strategy_id → list of equity curve points
        self._equity_curve: Dict[str, List[dict]] = {}
        # last time we sampled the equity curve per strategy
        self._last_sample_ts: Dict[str, Optional[datetime]] = {}

    def get_or_create(self, strategy_id: str, symbol: str) -> Position:
        if strategy_id not in self._positions:
            self._positions[strategy_id] = {}
            self._equity_curve[strategy_id] = []
            self._last_sample_ts[strategy_id] = None
        if symbol not in self._positions[strategy_id]:
            self._positions[strategy_id][symbol] = Position(strategy_id=strategy_id, symbol=symbol)
        return self._positions[strategy_id][symbol]

    def on_trade(self, trade: Trade) -> Position:
        pos = self.get_or_create(trade.strategy_id, trade.symbol)
        pos.apply_fill(trade.side, trade.quantity, trade.price)
        log.info(
            "position_updated",
            strategy=trade.strategy_id,
            symbol=trade.symbol,
            qty=pos.quantity,
            realized=round(pos.realized_pnl, 2),
        )
        return pos

    def mark_to_market(self, tick: Tick) -> List[Position]:
        updated = []
        affected_strategies: set[str] = set()

        for strategy_id, symbols in self._positions.items():
            if tick.symbol in symbols:
                pos = symbols[tick.symbol]
                pos.update_unrealized(tick.mid())
                updated.append(pos)
                affected_strategies.add(strategy_id)

        # Sample equity curve once per second per strategy, summed across all symbols
        now = tick.timestamp
        for strategy_id in affected_strategies:
            last_ts = self._last_sample_ts.get(strategy_id)
            elapsed = (now - last_ts).total_seconds() if last_ts else None
            if elapsed is None or elapsed >= _EQUITY_SAMPLE_INTERVAL_S:
                positions = self._positions[strategy_id]
                point = {
                    "timestamp": now.isoformat(),
                    "total_pnl": round(sum(p.total_pnl for p in positions.values()), 4),
                    "realized": round(sum(p.realized_pnl for p in positions.values()), 4),
                    "unrealized": round(sum(p.unrealized_pnl for p in positions.values()), 4),
                }
                self._equity_curve[strategy_id].append(point)
                self._last_sample_ts[strategy_id] = now
                if len(self._equity_curve[strategy_id]) > _EQUITY_CURVE_MAX:
                    self._equity_curve[strategy_id] = self._equity_curve[strategy_id][-_EQUITY_CURVE_MAX:]

        return updated

    def all_positions(self) -> List[Position]:
        result = []
        for symbols in self._positions.values():
            result.extend(symbols.values())
        return result

    def positions_for_strategy(self, strategy_id: str) -> List[Position]:
        return list(self._positions.get(strategy_id, {}).values())

    def equity_curve(self, strategy_id: str) -> List[dict]:
        return self._equity_curve.get(strategy_id, [])

    def summary(self) -> dict:
        out = {}
        for sid, symbols in self._positions.items():
            out[sid] = {
                "positions": [p.to_dict() for p in symbols.values()],
                "total_realized": round(sum(p.realized_pnl for p in symbols.values()), 2),
                "total_unrealized": round(sum(p.unrealized_pnl for p in symbols.values()), 2),
            }
        return out
