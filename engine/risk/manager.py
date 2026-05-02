"""
Risk Manager
------------
Pre-trade checks executed synchronously before an order reaches the
execution simulator.  Any breach immediately rejects the order.

Checks:
  1. Max notional per position (USD)
  2. Max drawdown from peak equity
  3. Max daily loss
"""
from __future__ import annotations
from typing import Dict
import structlog

from engine.models import Order, OrderSide, OrderStatus, Position
from engine.core.config import settings

log = structlog.get_logger(__name__)


class RiskManager:
    def __init__(self) -> None:
        self._positions: Dict[str, Dict[str, Position]] = {}   # strategy_id → symbol → Position
        self._peak_equity: Dict[str, float] = {}
        self._daily_pnl: Dict[str, float] = {}
        self._overrides: Dict[str, dict] = {}   # strategy_id → limit overrides
        self._initial_equity = 1_000_000.0  # $1M starting NAV per strategy

    def register_strategy(self, strategy_id: str) -> None:
        self._positions[strategy_id] = {}
        self._peak_equity[strategy_id] = self._initial_equity
        self._daily_pnl[strategy_id] = 0.0

    def update_position(self, strategy_id: str, position: Position) -> None:
        if strategy_id not in self._positions:
            self.register_strategy(strategy_id)
        self._positions[strategy_id][position.symbol] = position
        self._update_metrics(strategy_id)

    def apply_overrides(self, strategy_id: str, limits: dict) -> None:
        """Apply runtime per-strategy limit overrides (from API PATCH /risk)."""
        if strategy_id not in self._overrides:
            self._overrides[strategy_id] = {}
        self._overrides[strategy_id].update(limits)
        log.info("risk_limits_overridden", strategy_id=strategy_id, limits=limits)

    def check_order(self, order: Order, current_price: float) -> tuple[bool, str]:
        """
        Returns (approved: bool, reason: str).
        Mutates order.status/rejection_reason on failure.
        Per-strategy overrides take precedence over global settings.
        """
        strategy_id = order.strategy_id
        if strategy_id not in self._positions:
            self.register_strategy(strategy_id)

        ov = self._overrides.get(strategy_id, {})
        max_pos_usd = ov.get("max_position_usd", settings.max_position_usd)
        max_dd_pct = ov.get("max_drawdown_pct", settings.max_drawdown_pct)
        max_loss_usd = ov.get("max_daily_loss_usd", settings.max_daily_loss_usd)

        positions = self._positions[strategy_id]
        pos = positions.get(order.symbol)
        current_qty = pos.quantity if pos else 0.0

        # 1. Position notional check
        new_qty = (
            current_qty + order.quantity
            if order.side == OrderSide.BUY
            else current_qty - order.quantity
        )
        new_notional = abs(new_qty) * current_price
        if new_notional > max_pos_usd:
            reason = (
                f"Position notional ${new_notional:,.0f} exceeds limit "
                f"${max_pos_usd:,.0f}"
            )
            return self._reject(order, reason)

        # 2. Drawdown check
        equity = self._calc_equity(strategy_id)
        peak = self._peak_equity.get(strategy_id, equity)
        if peak > 0 and (peak - equity) / peak > max_dd_pct:
            reason = f"Drawdown {((peak - equity) / peak):.2%} exceeds limit {max_dd_pct:.2%}"
            return self._reject(order, reason)

        # 3. Daily loss check
        daily_pnl = self._daily_pnl.get(strategy_id, 0.0)
        if daily_pnl < -max_loss_usd:
            reason = f"Daily loss ${abs(daily_pnl):,.0f} exceeds limit ${max_loss_usd:,.0f}"
            return self._reject(order, reason)

        return True, "approved"

    def record_trade_pnl(self, strategy_id: str, pnl_delta: float) -> None:
        self._daily_pnl[strategy_id] = self._daily_pnl.get(strategy_id, 0.0) + pnl_delta
        self._update_metrics(strategy_id)

    def reset_daily(self) -> None:
        for sid in self._daily_pnl:
            self._daily_pnl[sid] = 0.0
        log.info("daily_risk_counters_reset")

    def get_risk_summary(self, strategy_id: str) -> dict:
        equity = self._calc_equity(strategy_id)
        peak = self._peak_equity.get(strategy_id, equity)
        drawdown = (peak - equity) / peak if peak > 0 else 0.0
        return {
            "strategy_id": strategy_id,
            "equity": round(equity, 2),
            "peak_equity": round(peak, 2),
            "drawdown_pct": round(drawdown * 100, 4),
            "daily_pnl": round(self._daily_pnl.get(strategy_id, 0.0), 2),
            "max_position_usd": settings.max_position_usd,
            "max_drawdown_pct": settings.max_drawdown_pct * 100,
            "max_daily_loss_usd": settings.max_daily_loss_usd,
        }

    # ── Internal ─────────────────────────────────────────────────────────────

    def _calc_equity(self, strategy_id: str) -> float:
        positions = self._positions.get(strategy_id, {})
        total_pnl = sum(p.total_pnl for p in positions.values())
        return self._initial_equity + total_pnl

    def _update_metrics(self, strategy_id: str) -> None:
        equity = self._calc_equity(strategy_id)
        peak = self._peak_equity.get(strategy_id, equity)
        if equity > peak:
            self._peak_equity[strategy_id] = equity

    @staticmethod
    def _reject(order: Order, reason: str) -> tuple[bool, str]:
        order.status = OrderStatus.REJECTED
        order.rejection_reason = reason
        log.warning("order_rejected_by_risk", order_id=order.id, reason=reason)
        return False, reason
