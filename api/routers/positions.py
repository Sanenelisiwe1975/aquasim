from __future__ import annotations
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_market_service, get_redis
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


@router.post("/{strategy_id}/{symbol}/liquidate", status_code=202)
async def liquidate_position(
    strategy_id: str,
    symbol: str,
    svc: MarketService = Depends(get_market_service),
    redis=Depends(get_redis),
):
    """Submit a market order to fully close the position.

    Returns 202 immediately; the fill is asynchronous.
    """
    sym = symbol.upper()
    pos = await svc.get_position(strategy_id, sym)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No position found for {strategy_id}/{sym}")

    qty = pos.get("quantity", 0.0)
    if qty == 0.0:
        return {"message": "Position is already flat", "quantity": 0.0}

    side = "SELL" if qty > 0 else "BUY"
    command = {
        "type": "submit_order",
        "order": {
            "id": str(uuid.uuid4()),
            "strategy_id": strategy_id,
            "symbol": sym,
            "side": side,
            "quantity": abs(qty),
            "order_type": "MARKET",
            "limit_price": None,
            "created_at": datetime.utcnow().isoformat(),
        },
    }
    await redis.publish("engine_commands", json.dumps(command))
    return {
        "strategy_id": strategy_id,
        "symbol": sym,
        "side": side,
        "quantity": abs(qty),
        "status": "liquidation_accepted",
    }
