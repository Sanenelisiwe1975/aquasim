"""Kafka topic name constants — single source of truth for all producers/consumers."""

MARKET_TICKS = "market_ticks"
ORDERBOOK_UPDATES = "orderbook_updates"
ORDERS = "orders"
TRADES = "trades"
POSITIONS = "positions"
PNL_UPDATES = "pnl_updates"
RISK_EVENTS = "risk_events"

ALL_TOPICS = [
    MARKET_TICKS,
    ORDERBOOK_UPDATES,
    ORDERS,
    TRADES,
    POSITIONS,
    PNL_UPDATES,
    RISK_EVENTS,
]
