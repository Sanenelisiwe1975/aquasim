from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_market_service
from api.services import MarketService

router = APIRouter(prefix="/strategies", tags=["strategies"])


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
