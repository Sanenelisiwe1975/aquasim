from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass(slots=True)
class Trade:
    order_id: str
    strategy_id: str
    symbol: str
    side: str          # "BUY" | "SELL"
    quantity: float
    price: float
    timestamp: datetime
    latency_us: int    # simulated fill latency in microseconds
    slippage: float    # price impact beyond quoted mid
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def notional(self) -> float:
        return self.quantity * self.price

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "notional": self.notional,
            "timestamp": self.timestamp.isoformat(),
            "latency_us": self.latency_us,
            "slippage": self.slippage,
        }
