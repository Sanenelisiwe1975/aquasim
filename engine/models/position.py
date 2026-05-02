from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Position:
    strategy_id: str
    symbol: str
    quantity: float = 0.0       # positive = long, negative = short
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_price: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)

    @property
    def notional(self) -> float:
        return abs(self.quantity) * self.last_price

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    def update_unrealized(self, current_price: float) -> None:
        self.last_price = current_price
        if self.quantity != 0:
            self.unrealized_pnl = (current_price - self.avg_entry_price) * self.quantity
        self.last_updated = datetime.utcnow()

    def apply_fill(self, side: str, quantity: float, price: float) -> None:
        """FIFO average-cost position accounting."""
        fill_qty = quantity if side == "BUY" else -quantity
        prev_qty = self.quantity
        new_qty = prev_qty + fill_qty

        if prev_qty == 0:
            self.avg_entry_price = price
        elif (prev_qty > 0 and fill_qty > 0) or (prev_qty < 0 and fill_qty < 0):
            # Adding to position — weighted average
            self.avg_entry_price = (
                (abs(prev_qty) * self.avg_entry_price + abs(fill_qty) * price)
                / abs(new_qty)
            )
        else:
            # Reducing or reversing — book realized PnL on closed portion
            closed = min(abs(prev_qty), abs(fill_qty))
            direction = 1 if prev_qty > 0 else -1
            self.realized_pnl += direction * closed * (price - self.avg_entry_price)
            if abs(fill_qty) > abs(prev_qty):
                # Reversal: reset avg to fill price for the new leg
                self.avg_entry_price = price

        self.quantity = new_qty
        self.last_price = price
        self.unrealized_pnl = (
            (self.last_price - self.avg_entry_price) * self.quantity
            if self.quantity != 0
            else 0.0
        )
        self.last_updated = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_entry_price": self.avg_entry_price,
            "last_price": self.last_price,
            "realized_pnl": round(self.realized_pnl, 4),
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "total_pnl": round(self.total_pnl, 4),
            "notional": round(self.notional, 2),
            "last_updated": self.last_updated.isoformat(),
        }
