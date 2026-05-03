from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db

router = APIRouter(prefix="/trades", tags=["trades"])


def _parse_ts(value: Optional[str], param: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp query parameter, raising 422 on bad input."""
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
    db:          AsyncSession  = Depends(get_db),
):
    from engine.db.models import TradeRecord

    stmt = select(TradeRecord).order_by(desc(TradeRecord.timestamp)).limit(limit)
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
            "id":          r.id,
            "order_id":    r.order_id,
            "strategy_id": r.strategy_id,
            "symbol":      r.symbol,
            "side":        r.side,
            "quantity":    r.quantity,
            "price":       r.price,
            "notional":    r.notional,
            "latency_us":  r.latency_us,
            "slippage":    r.slippage,
            "timestamp":   r.timestamp.isoformat(),
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
    agg_stmt = _apply_filters(
        select(
            func.count(TradeRecord.id).label("total"),
            func.sum(TradeRecord.notional).label("total_notional"),
            func.avg(TradeRecord.latency_us).label("avg_latency_us"),
            func.avg(TradeRecord.slippage).label("avg_slippage"),
        )
    )
    agg_row = (await db.execute(agg_stmt)).one()

    # Per-symbol breakdown (aggregated in Python to stay dialect-agnostic)
    detail_rows = (
        await db.execute(
            _apply_filters(
                select(TradeRecord.symbol, TradeRecord.side, TradeRecord.notional)
            )
        )
    ).all()

    by_symbol: dict = {}
    for symbol, side, notional in detail_rows:
        s = by_symbol.setdefault(
            symbol, {"trades": 0, "notional": 0.0, "buy_count": 0, "sell_count": 0}
        )
        s["trades"]   += 1
        s["notional"] += notional or 0.0
        if side == "BUY":
            s["buy_count"]  += 1
        else:
            s["sell_count"] += 1

    for s in by_symbol.values():
        s["notional"] = round(s["notional"], 2)

    return {
        "strategy_id":    strategy_id,
        "total_trades":   agg_row.total or 0,
        "total_notional": round(agg_row.total_notional or 0, 2),
        "avg_latency_us": round(agg_row.avg_latency_us or 0, 1),
        "avg_slippage":   round(agg_row.avg_slippage or 0, 6),
        "by_symbol":      by_symbol,
    }
