from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from api.dependencies import get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _serialize_run(r) -> dict:
    return {
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
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/runs")
async def list_runs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    from engine.db.models import BacktestRun

    result = await db.execute(
        select(BacktestRun).order_by(desc(BacktestRun.created_at)).limit(limit)
    )
    return [_serialize_run(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    from engine.db.models import BacktestRun

    result = await db.execute(select(BacktestRun).where(BacktestRun.id == run_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return _serialize_run(row)
