from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_market_service
from api.services import MarketService

router = APIRouter(prefix="/orderbook", tags=["orderbook"])


@router.get("/{symbol}")
async def get_orderbook(symbol: str, svc: MarketService = Depends(get_market_service)):
    book = await svc.get_orderbook(symbol.upper())
    if not book:
        raise HTTPException(status_code=404, detail=f"No order book for {symbol}")
    return book


@router.get("/{symbol}/ticks")
async def get_ticks(symbol: str, n: int = 100, svc: MarketService = Depends(get_market_service)):
    return await svc.get_ticks(symbol.upper(), n)
