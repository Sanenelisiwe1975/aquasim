from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db

router = APIRouter(prefix="/trades", tags=["trades"])


def _parse_ts(value: Optional[str], param: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {param}: {value!r}")


@router.get("/")
async def list_trades(
    strategy_id: Optional[str] = Query(None),
    symbol:      Optional[str] = Query(None),
    from_ts:     Optional[str] = Query(None, description="ISO-8601 start timestamp (inclusive)"),
    to_ts:       Optional[str] = Query(None, description="ISO-8601 end timestamp (inclusive)"),
    limit:       int           = Query(100, le=1000),
    offset:      int           = Query(0, ge=0),
    db:          AsyncSession  = Depends(get_db),
):
    from engine.db.models import TradeRecord

    stmt = (
        select(TradeRecord)
        .order_by(desc(TradeRecord.timestamp))
        .offset(offset)
        .limit(limit)
    )
    if strategy_id:
        stmt = stmt.where(TradeRecord.strategy_id == strategy_id)
    if symbol:
        stmt = stmt.where(TradeRecord.symbol == symbol.upper())
    if dt := _parse_ts(from_ts, "from_ts"):
        stmt = stmt.where(TradeRecord.timestamp >= dt)
    if dt := _parse_ts(to_ts, "to_ts"):
        stmt = stmt.where(TradeRecord.timestamp <= dt)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id":            r.id,
            "order_id":      r.order_id,
            "strategy_id":   r.strategy_id,
            "symbol":        r.symbol,
            "side":          r.side,
            "quantity":      r.quantity,
            "price":         r.price,
            "notional":      r.notional,
            "latency_us":    r.latency_us,
            "slippage":      r.slippage,
            "realized_pnl":  r.realized_pnl,
            "timestamp":     r.timestamp.isoformat(),
        }
        for r in rows
    ]


@router.get("/stats/{strategy_id}")
async def trade_stats(
    strategy_id: str,
    from_ts:     Optional[str] = Query(None, description="ISO-8601 start timestamp"),
    to_ts:       Optional[str] = Query(None, description="ISO-8601 end timestamp"),
    db:          AsyncSession  = Depends(get_db),
):
    from engine.db.models import TradeRecord

    dt_from = _parse_ts(from_ts, "from_ts")
    dt_to   = _parse_ts(to_ts,   "to_ts")

    def _apply_filters(stmt):
        stmt = stmt.where(TradeRecord.strategy_id == strategy_id)
        if dt_from:
            stmt = stmt.where(TradeRecord.timestamp >= dt_from)
        if dt_to:
            stmt = stmt.where(TradeRecord.timestamp <= dt_to)
        return stmt

    # Overall aggregates
    agg_row = (
        await db.execute(
            _apply_filters(
                select(
                    func.count(TradeRecord.id).label("total"),
                    func.sum(TradeRecord.notional).label("total_notional"),
                    func.avg(TradeRecord.latency_us).label("avg_latency_us"),
                    func.avg(TradeRecord.slippage).label("avg_slippage"),
                    func.sum(TradeRecord.realized_pnl).label("total_realized_pnl"),
                )
            )
        )
    ).one()

    # Per-trade detail for per-symbol breakdown and win rate
    detail_rows = (
        await db.execute(
            _apply_filters(
                select(
                    TradeRecord.symbol,
                    TradeRecord.side,
                    TradeRecord.notional,
                    TradeRecord.realized_pnl,
                )
            )
        )
    ).all()

    by_symbol: dict = {}
    wins = losses = 0

    for symbol, side, notional, realized_pnl in detail_rows:
        s = by_symbol.setdefault(
            symbol,
            {"trades": 0, "notional": 0.0, "buy_count": 0, "sell_count": 0,
             "realized_pnl": 0.0},
        )
        s["trades"]       += 1
        s["notional"]     += notional or 0.0
        s["realized_pnl"] += realized_pnl or 0.0
        if side == "BUY":
            s["buy_count"] += 1
        else:
            s["sell_count"] += 1

        # Count only closing fills (those that book PnL) for win rate
        if realized_pnl and realized_pnl != 0.0:
            if realized_pnl > 0:
                wins += 1
            else:
                losses += 1

    for s in by_symbol.values():
        s["notional"]     = round(s["notional"], 2)
        s["realized_pnl"] = round(s["realized_pnl"], 2)

    total_closing = wins + losses
    win_rate = round(wins / total_closing, 4) if total_closing > 0 else None

    return {
        "strategy_id":       strategy_id,
        "total_trades":      agg_row.total or 0,
        "total_notional":    round(agg_row.total_notional or 0, 2),
        "total_realized_pnl":round(agg_row.total_realized_pnl or 0, 2),
        "avg_latency_us":    round(agg_row.avg_latency_us or 0, 1),
        "avg_slippage":      round(agg_row.avg_slippage or 0, 6),
        "win_rate":          win_rate,
        "wins":              wins,
        "losses":            losses,
        "by_symbol":         by_symbol,
    }
