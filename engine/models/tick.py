from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Tick:
    symbol: str
    price: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    volume: float
    timestamp: datetime
    sequence: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Tick":
        """Deserialise a tick dict with explicit type coercion.

        Raises KeyError/ValueError on missing or unparseable required fields
        so the caller gets a clear error rather than a silent bad state.
        """
        return cls(
            symbol=str(d["symbol"]),
            price=float(d["price"]),
            bid=float(d["bid"]),
            ask=float(d["ask"]),
            bid_size=float(d.get("bid_size", 100.0)),
            ask_size=float(d.get("ask_size", 100.0)),
            volume=float(d.get("volume", 0.0)),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            sequence=int(d.get("sequence", 0)),
        )

    def spread(self) -> float:
        return self.ask - self.bid

    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
        }
