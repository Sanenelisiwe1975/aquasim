from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/")
async def list_trades(
    strategy_id: Optional[str]  = Query(None),
    symbol:      Optional[str]  = Query(None),
    from_ts:     Optional[str]  = Query(None, description="ISO-8601 start timestamp (inclusive)"),
    to_ts:       Optional[str]  = Query(None, description="ISO-8601 end timestamp (inclusive)"),
    limit:       int            = Query(100, le=1000),
    db:          AsyncSession   = Depends(get_db),
):
    from engine.db.models import TradeRecord

    stmt = select(TradeRecord).order_by(desc(TradeRecord.timestamp)).limit(limit)
    if strategy_id:
        stmt = stmt.where(TradeRecord.strategy_id == strategy_id)
    if symbol:
        stmt = stmt.where(TradeRecord.symbol == symbol.upper())
    if from_ts:
        try:
            stmt = stmt.where(TradeRecord.timestamp >= datetime.fromisoformat(from_ts))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid from_ts: {from_ts!r}")
    if to_ts:
        try:
            stmt = stmt.where(TradeRecord.timestamp <= datetime.fromisoformat(to_ts))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid to_ts: {to_ts!r}")

    result = await db.execute(stmt)
    rows   = result.scalars().all()
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

    base = select(TradeRecord).where(TradeRecord.strategy_id == strategy_id)
    if from_ts:
        try:
            base = base.where(TradeRecord.timestamp >= datetime.fromisoformat(from_ts))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid from_ts: {from_ts!r}")
    if to_ts:
        try:
            base = base.where(TradeRecord.timestamp <= datetime.fromisoformat(to_ts))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid to_ts: {to_ts!r}")

    # Overall aggregates
    agg_stmt = select(
        func.count(TradeRecord.id).label("total"),
        func.sum(TradeRecord.notional).label("total_notional"),
        func.avg(TradeRecord.latency_us).label("avg_latency_us"),
        func.avg(TradeRecord.slippage).label("avg_slippage"),
    ).where(TradeRecord.strategy_id == strategy_id)
    if from_ts:
        agg_stmt = agg_stmt.where(TradeRecord.timestamp >= datetime.fromisoformat(from_ts))
    if to_ts:
        agg_stmt = agg_stmt.where(TradeRecord.timestamp <= datetime.fromisoformat(to_ts))

    agg_row = (await db.execute(agg_stmt)).one()

    # Per-symbol breakdown — aggregate in Python to avoid dialect-specific CAST quirks
    all_rows_result = await db.execute(
        select(TradeRecord.symbol, TradeRecord.side, TradeRecord.notional)
        .where(TradeRecord.strategy_id == strategy_id)
        .where(*(
            ([TradeRecord.timestamp >= datetime.fromisoformat(from_ts)] if from_ts else []) +
            ([TradeRecord.timestamp <= datetime.fromisoformat(to_ts)]   if to_ts   else [])
        ) or [True])
    )
    all_rows = all_rows_result.all()

    by_symbol: dict = {}
    for symbol, side, notional in all_rows:
        s = by_symbol.setdefault(symbol, {"trades": 0, "notional": 0.0, "buy_count": 0, "sell_count": 0})
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
