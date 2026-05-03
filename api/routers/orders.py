from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_redis

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderRequest(BaseModel):
    strategy_id: str
    symbol: str
    side: str = Field(pattern="^(BUY|SELL|buy|sell)$")
    quantity: float = Field(gt=0)
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT|market|limit)$")
    limit_price: Optional[float] = Field(default=None, gt=0)


def _serialize_order(r) -> dict:
    return {
        "id": r.id,
        "strategy_id": r.strategy_id,
        "symbol": r.symbol,
        "side": r.side,
        "quantity": r.quantity,
        "order_type": r.order_type,
        "limit_price": r.limit_price,
        "status": r.status,
        "filled_price": r.filled_price,
        "filled_quantity": r.filled_quantity,
        "rejection_reason": r.rejection_reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "filled_at": r.filled_at.isoformat() if r.filled_at else None,
    }


@router.get("/")
async def list_orders(
    strategy_id: Optional[str] = Query(None),
    symbol:      Optional[str] = Query(None),
    status:      Optional[str] = Query(None),
    limit:       int           = Query(100, le=1000),
    offset:      int           = Query(0, ge=0),
    db:          AsyncSession  = Depends(get_db),
):
    from engine.db.models import OrderRecord

    stmt = select(OrderRecord).order_by(desc(OrderRecord.created_at)).offset(offset).limit(limit)
    if strategy_id:
        stmt = stmt.where(OrderRecord.strategy_id == strategy_id)
    if symbol:
        stmt = stmt.where(OrderRecord.symbol == symbol.upper())
    if status:
        stmt = stmt.where(OrderRecord.status == status.upper())

    result = await db.execute(stmt)
    return [_serialize_order(r) for r in result.scalars().all()]


@router.get("/{order_id}")
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    from engine.db.models import OrderRecord

    result = await db.execute(select(OrderRecord).where(OrderRecord.id == order_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return _serialize_order(row)


@router.post("/", status_code=202)
async def submit_order(req: OrderRequest, redis=Depends(get_redis)):
    """Route a manual order to the engine via Redis command channel.

    Returns immediately with the assigned order ID; the fill is asynchronous.
    Poll GET /orders/{order_id} to check fill status.
    """
    order_id = str(uuid.uuid4())
    command = {
        "type": "submit_order",
        "order": {
            "id": order_id,
            "strategy_id": req.strategy_id,
            "symbol": req.symbol.upper(),
            "side": req.side.upper(),
            "quantity": req.quantity,
            "order_type": req.order_type.upper(),
            "limit_price": req.limit_price,
            "created_at": datetime.utcnow().isoformat(),
        },
    }
    await redis.publish("engine_commands", json.dumps(command))
    return {"order_id": order_id, "status": "accepted"}
