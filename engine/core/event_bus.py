"""
Internal async event bus.  Components publish typed events; subscribers receive
them via asyncio queues — fully decoupled, zero Kafka overhead for intra-process
signalling.
"""
import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List, Type
import structlog

log = structlog.get_logger(__name__)


class EventBus:
    def __init__(self) -> None:
        # event_type,list of async handler coroutines
        self._handlers: Dict[str, List[Callable[..., Coroutine]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[..., Coroutine]) -> None:
        self._handlers[event_type].append(handler)
        log.debug("subscribed", event_type=event_type, handler=handler.__qualname__)

    async def publish(self, event_type: str, payload: Any) -> None:
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return
        # Fire all handlers concurrently; errors are logged but don't crash the bus.
        results = await asyncio.gather(
            *[h(payload) for h in handlers], return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                log.error("event_handler_error", event_type=event_type, error=str(r))


# Module-level singleton shared by all engine components.
bus = EventBus()

# Well-known event type constants.
EVT_TICK = "tick"
EVT_ORDERBOOK = "orderbook"
EVT_ORDER_NEW = "order.new"
EVT_ORDER_FILLED = "order.filled"
EVT_ORDER_REJECTED = "order.rejected"
EVT_TRADE = "trade"
EVT_POSITION_UPDATE = "position.update"
EVT_PNL_UPDATE = "pnl.update"
EVT_RISK_BREACH = "risk.breach"
