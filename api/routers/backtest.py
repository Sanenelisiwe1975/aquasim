from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from api.dependencies import get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/runs")
async def list_runs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    from engine.db.models import BacktestRun

    result = await db.execute(
        select(BacktestRun).order_by(desc(BacktestRun.created_at)).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "strategy_id": r.strategy_id,
            "symbol": r.symbol,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "total_trades": r.total_trades,
            "realized_pnl": r.realized_pnl,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "win_rate": r.win_rate,
            "completed": r.completed,
        }
        for r in rows
    ]
