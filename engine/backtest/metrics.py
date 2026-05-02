"""
Backtest Metrics
----------------
Computes summary statistics from an in-memory equity curve produced by
PnLTracker.  All metrics are strategy-level (aggregated across symbols).

equity_curve entries: {"timestamp": str, "total_pnl": float,
                       "realized": float, "unrealized": float}
"""
from __future__ import annotations
import math
import statistics
from typing import Any


def compute_backtest_metrics(equity_curve: list[dict[str, Any]]) -> dict[str, Any]:
    """Return sharpe_ratio, max_drawdown, win_rate, realized_pnl."""
    if not equity_curve:
        return {"sharpe_ratio": None, "max_drawdown": 0.0, "win_rate": 0.0, "realized_pnl": 0.0}

    realized_pnl = equity_curve[-1].get("realized", 0.0)
    sharpe = _sharpe(equity_curve)
    max_dd = _max_drawdown(equity_curve)
    win_rate = _win_rate(equity_curve)

    return {
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "realized_pnl": realized_pnl,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sharpe(equity_curve: list[dict]) -> float | None:
    """Annualised Sharpe from tick-level total_pnl series.

    Assumes 100 ms per sample → 10 samples/s.
    Annualisation factor: sqrt(252 trading days × 6.5 h × 3600 s × 10 samples/s).
    """
    if len(equity_curve) < 2:
        return None
    pnls = [e["total_pnl"] for e in equity_curve]
    returns = [pnls[i] - pnls[i - 1] for i in range(1, len(pnls))]
    if len(returns) < 2:
        return None
    mean_r = statistics.mean(returns)
    std_r = statistics.pstdev(returns)
    if std_r == 0.0:
        return None
    samples_per_year = 252 * 6.5 * 3600 * 10
    annualisation = math.sqrt(samples_per_year)
    return round((mean_r / std_r) * annualisation, 4)


def _max_drawdown(equity_curve: list[dict]) -> float:
    """Maximum peak-to-trough decline in total_pnl (absolute value, USD)."""
    peak = equity_curve[0]["total_pnl"]
    max_dd = 0.0
    for point in equity_curve[1:]:
        pnl = point["total_pnl"]
        if pnl > peak:
            peak = pnl
        drawdown = peak - pnl
        if drawdown > max_dd:
            max_dd = drawdown
    return round(max_dd, 4)


def _win_rate(equity_curve: list[dict]) -> float:
    """Fraction of fill events where realized PnL increased.

    Each tick where realized PnL changes represents a position close/reduce.
    Ticks with no change are ignored.
    """
    wins = losses = 0
    prev = equity_curve[0].get("realized", 0.0)
    for point in equity_curve[1:]:
        curr = point.get("realized", 0.0)
        delta = curr - prev
        if delta > 1e-6:
            wins += 1
        elif delta < -1e-6:
            losses += 1
        prev = curr
    total = wins + losses
    return round(wins / total, 4) if total > 0 else 0.0
