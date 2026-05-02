from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/")
async def list_trades(
    strategy_id: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    # Import here to avoid circular deps at module load
    from sqlalchemy import text
    from engine.db.models import TradeRecord

    stmt = select(TradeRecord).order_by(desc(TradeRecord.timestamp)).limit(limit)
    if strategy_id:
        stmt = stmt.where(TradeRecord.strategy_id == strategy_id)
    if symbol:
        stmt = stmt.where(TradeRecord.symbol == symbol.upper())

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "order_id": r.order_id,
            "strategy_id": r.strategy_id,
            "symbol": r.symbol,
            "side": r.side,
            "quantity": r.quantity,
            "price": r.price,
            "notional": r.notional,
            "latency_us": r.latency_us,
            "slippage": r.slippage,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in rows
    ]


@router.get("/stats/{strategy_id}")
async def trade_stats(strategy_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    from engine.db.models import TradeRecord

    result = await db.execute(
        select(
            func.count(TradeRecord.id).label("total"),
            func.sum(TradeRecord.notional).label("total_notional"),
            func.avg(TradeRecord.latency_us).label("avg_latency_us"),
            func.avg(TradeRecord.slippage).label("avg_slippage"),
        ).where(TradeRecord.strategy_id == strategy_id)
    )
    row = result.one()
    return {
        "strategy_id": strategy_id,
        "total_trades": row.total or 0,
        "total_notional": round(row.total_notional or 0, 2),
        "avg_latency_us": round(row.avg_latency_us or 0, 1),
        "avg_slippage": round(row.avg_slippage or 0, 6),
    }
