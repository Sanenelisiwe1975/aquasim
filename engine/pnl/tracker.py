"""
PnL Tracker
-----------
Maintains per-strategy, per-symbol positions.  On every tick it marks
all open positions to market.  Publishes snapshots to the event bus and Redis.
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, List
import json
import structlog

from engine.models import Position, Tick, Trade

log = structlog.get_logger(__name__)


class PnLTracker:
    def __init__(self) -> None:
        # strategy_id → symbol → Position
        self._positions: Dict[str, Dict[str, Position]] = {}
        # strategy_id → list of (timestamp, total_pnl) samples for equity curve
        self._equity_curve: Dict[str, List[dict]] = {}

    def get_or_create(self, strategy_id: str, symbol: str) -> Position:
        if strategy_id not in self._positions:
            self._positions[strategy_id] = {}
            self._equity_curve[strategy_id] = []
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
        for strategy_id, symbols in self._positions.items():
            if tick.symbol in symbols:
                pos = symbols[tick.symbol]
                pos.update_unrealized(tick.mid())
                updated.append(pos)
                # Sample equity curve every tick
                self._equity_curve[strategy_id].append({
                    "timestamp": tick.timestamp.isoformat(),
                    "total_pnl": round(pos.total_pnl, 4),
                    "realized": round(pos.realized_pnl, 4),
                    "unrealized": round(pos.unrealized_pnl, 4),
                })
                # Keep curve bounded to last 10_000 points in memory
                if len(self._equity_curve[strategy_id]) > 10_000:
                    self._equity_curve[strategy_id] = self._equity_curve[strategy_id][-10_000:]
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
