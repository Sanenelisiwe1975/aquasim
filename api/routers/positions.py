from fastapi import APIRouter, Depends
from api.dependencies import get_market_service
from api.services import MarketService

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/")
async def all_positions(svc: MarketService = Depends(get_market_service)):
    return await svc.get_all_positions()


@router.get("/{strategy_id}")
async def strategy_positions(strategy_id: str, svc: MarketService = Depends(get_market_service)):
    return await svc.get_positions(strategy_id)


@router.get("/{strategy_id}/equity-curve")
async def equity_curve(
    strategy_id: str, n: int = 500, svc: MarketService = Depends(get_market_service)
):
    return await svc.get_equity_curve(strategy_id, n)
