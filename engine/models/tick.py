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
