"""
In-process L2 order book.  Bid/ask levels stored as sorted dicts.
State is mirrored to Redis after every update for cross-process reads.
"""
from __future__ import annotations
import json
from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import structlog

log = structlog.get_logger(__name__)


class OrderBook:
    def __init__(self, symbol: str, depth: int = 10) -> None:
        self.symbol = symbol
        self.depth = depth
        # price → size, kept sorted (bids desc, asks asc)
        self._bids: Dict[float, float] = {}
        self._asks: Dict[float, float] = {}
        self.last_trade_price: float = 0.0
        self.sequence: int = 0
        self.updated_at: datetime = datetime.utcnow()

    # ── Mutation ────────────────────────────────────────────────────────────

    def update_from_tick(
        self,
        bid: float,
        ask: float,
        bid_size: float,
        ask_size: float,
        price: float,
        extra_levels: Optional[List[Tuple[float, float, str]]] = None,
    ) -> None:
        """Apply a top-of-book tick and optional synthetic deeper levels."""
        self._bids[bid] = bid_size
        self._asks[ask] = ask_size
        self.last_trade_price = price

        if extra_levels:
            for lvl_price, lvl_size, side in extra_levels:
                if side == "bid":
                    self._bids[lvl_price] = lvl_size
                else:
                    self._asks[lvl_price] = lvl_size

        self._trim()
        self.sequence += 1
        self.updated_at = datetime.utcnow()

    def apply_snapshot(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]) -> None:
        self._bids = {p: s for p, s in bids}
        self._asks = {p: s for p, s in asks}
        self._trim()
        self.sequence += 1
        self.updated_at = datetime.utcnow()

    # ── Accessors ────────────────────────────────────────────────────────────

    def best_bid(self) -> Optional[Tuple[float, float]]:
        if not self._bids:
            return None
        p = max(self._bids)
        return p, self._bids[p]

    def best_ask(self) -> Optional[Tuple[float, float]]:
        if not self._asks:
            return None
        p = min(self._asks)
        return p, self._asks[p]

    def mid_price(self) -> Optional[float]:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb and ba:
            return (bb[0] + ba[0]) / 2.0
        return None

    def spread(self) -> Optional[float]:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb and ba:
            return ba[0] - bb[0]
        return None

    def bids(self, n: Optional[int] = None) -> List[Tuple[float, float]]:
        levels = sorted(self._bids.items(), key=lambda x: -x[0])
        return levels[: n or self.depth]

    def asks(self, n: Optional[int] = None) -> List[Tuple[float, float]]:
        levels = sorted(self._asks.items())
        return levels[: n or self.depth]

    def available_liquidity(self, side: str, price_limit: float) -> float:
        """Total size available up to price_limit on the given side."""
        if side == "BUY":
            return sum(s for p, s in self._asks.items() if p <= price_limit)
        return sum(s for p, s in self._bids.items() if p >= price_limit)

    def simulate_market_impact(self, side: str, quantity: float) -> float:
        """Walk the book and return average fill price for a market order."""
        remaining = quantity
        total_cost = 0.0
        levels = self.asks() if side == "BUY" else self.bids()

        for price, size in levels:
            fill = min(remaining, size)
            total_cost += fill * price
            remaining -= fill
            if remaining <= 0:
                break

        if remaining > 0:
            # Not enough liquidity — fill rest at worst level price (slippage)
            worst = levels[-1][0] if levels else self.last_trade_price
            total_cost += remaining * worst

        return total_cost / quantity if quantity > 0 else 0.0

    # ── Serialisation ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "sequence": self.sequence,
            "timestamp": self.updated_at.isoformat(),
            "last_trade_price": self.last_trade_price,
            "bids": self.bids(),
            "asks": self.asks(),
            "mid": self.mid_price(),
            "spread": self.spread(),
        }

    def to_redis_payload(self) -> str:
        d = self.to_dict()
        d["bids"] = [[p, s] for p, s in d["bids"]]
        d["asks"] = [[p, s] for p, s in d["asks"]]
        return json.dumps(d)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _trim(self) -> None:
        """Keep only top-N levels to bound memory."""
        if len(self._bids) > self.depth:
            sorted_bids = sorted(self._bids.items(), key=lambda x: -x[0])
            self._bids = dict(sorted_bids[: self.depth])
        if len(self._asks) > self.depth:
            sorted_asks = sorted(self._asks.items())
            self._asks = dict(sorted_asks[: self.depth])
