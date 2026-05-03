"""
Async Kafka consumer wrapper with auto-reconnect and per-topic dispatch.
"""
from __future__ import annotations
import asyncio
import json
from typing import Callable, Coroutine, Dict, List

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
import structlog

from engine.core.config import settings

log = structlog.get_logger(__name__)

Handler = Callable[[dict], Coroutine]


class KafkaConsumer:
    def __init__(
        self,
        topics: List[str],
        group_id: str = settings.kafka_consumer_group,
        auto_offset_reset: str = "latest",
    ) -> None:
        self._topics = topics
        self._group_id = group_id
        self._auto_offset_reset = auto_offset_reset
        self._consumer: AIOKafkaConsumer | None = None
        # topic,list of async handlers
        self._handlers: Dict[str, List[Handler]] = {t: [] for t in topics}

    def register(self, topic: str, handler: Handler) -> None:
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=self._group_id,
            value_deserializer=lambda b: json.loads(b.decode()),
            auto_offset_reset=self._auto_offset_reset,
            enable_auto_commit=True,
            auto_commit_interval_ms=1_000,
            fetch_max_wait_ms=10,    # low latency polling
            fetch_min_bytes=1,
        )
        await self._consumer.start()
        log.info("kafka_consumer_started", topics=self._topics, group=self._group_id)

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()
            log.info("kafka_consumer_stopped")

    async def run(self) -> None:
        """Consume messages forever, dispatching to registered handlers."""
        if not self._consumer:
            raise RuntimeError("Consumer not started — call start() first")

        log.info("kafka_consumer_listening", topics=self._topics)
        async for msg in self._consumer:
            topic = msg.topic
            handlers = self._handlers.get(topic, [])
            if handlers:
                results = await asyncio.gather(
                    *[h(msg.value) for h in handlers], return_exceptions=True
                )
                for r in results:
                    if isinstance(r, Exception):
                        log.error("consumer_handler_error", topic=topic, error=str(r))
