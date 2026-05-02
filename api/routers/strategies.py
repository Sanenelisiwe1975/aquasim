from __future__ import annotations
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_market_service, get_redis
from api.services import MarketService

router = APIRouter(prefix="/strategies", tags=["strategies"])


class RiskLimitUpdate(BaseModel):
    max_position_usd: Optional[float] = Field(default=None, gt=0)
    max_drawdown_pct: Optional[float] = Field(default=None, gt=0, le=1)
    max_daily_loss_usd: Optional[float] = Field(default=None, gt=0)


@router.get("/")
async def list_strategies(svc: MarketService = Depends(get_market_service)):
    ids = await svc.get_strategy_ids()
    return {"strategies": ids}


@router.get("/{strategy_id}/risk")
async def get_risk(strategy_id: str, svc: MarketService = Depends(get_market_service)):
    risk = await svc.get_risk(strategy_id)
    if not risk:
        raise HTTPException(status_code=404, detail=f"No risk data for {strategy_id}")
    return risk


@router.get("/{strategy_id}/summary")
async def get_summary(strategy_id: str, svc: MarketService = Depends(get_market_service)):
    positions = await svc.get_positions(strategy_id)
    risk = await svc.get_risk(strategy_id)
    curve = await svc.get_equity_curve(strategy_id, n=1)
    latest_pnl = curve[-1] if curve else {"total_pnl": 0.0}
    return {
        "strategy_id": strategy_id,
        "positions": positions,
        "risk": risk,
        "latest_pnl": latest_pnl,
    }


@router.get("/{strategy_id}/status")
async def get_status(strategy_id: str, redis=Depends(get_redis)):
    paused_flag = await redis.get(f"strategy:{strategy_id}:paused")
    return {"strategy_id": strategy_id, "paused": paused_flag == "1"}


@router.post("/{strategy_id}/pause", status_code=202)
async def pause_strategy(strategy_id: str, redis=Depends(get_redis)):
    await redis.set(f"strategy:{strategy_id}:paused", "1")
    await redis.publish(
        "engine_commands",
        json.dumps({"type": "pause_strategy", "strategy_id": strategy_id}),
    )
    return {"strategy_id": strategy_id, "status": "pausing"}


@router.post("/{strategy_id}/resume", status_code=202)
async def resume_strategy(strategy_id: str, redis=Depends(get_redis)):
    await redis.set(f"strategy:{strategy_id}:paused", "0")
    await redis.publish(
        "engine_commands",
        json.dumps({"type": "resume_strategy", "strategy_id": strategy_id}),
    )
    return {"strategy_id": strategy_id, "status": "resuming"}


@router.patch("/{strategy_id}/risk")
async def update_risk_limits(
    strategy_id: str,
    update: RiskLimitUpdate,
    redis=Depends(get_redis),
):
    limits = {k: v for k, v in update.dict().items() if v is not None}
    if not limits:
        raise HTTPException(status_code=400, detail="No valid limit fields provided")
    await redis.set(f"risk_override:{strategy_id}", json.dumps(limits))
    await redis.publish(
        "engine_commands",
        json.dumps({"type": "update_risk", "strategy_id": strategy_id, "limits": limits}),
    )
    return {"strategy_id": strategy_id, "updated_limits": limits}
