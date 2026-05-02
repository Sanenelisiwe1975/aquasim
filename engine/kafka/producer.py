"""
Async Kafka producer wrapper.
Serialises all messages as JSON bytes.
"""
from __future__ import annotations
import json
from typing import Any

from aiokafka import AIOKafkaProducer
import structlog

from engine.core.config import settings

log = structlog.get_logger(__name__)


class KafkaProducer:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            compression_type="gzip",
            # Tuned for low latency — ack from leader only, no lingering
            acks=1,
            linger_ms=0,
            request_timeout_ms=5_000,
        )
        await self._producer.start()
        log.info("kafka_producer_started", brokers=settings.kafka_bootstrap_servers)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            log.info("kafka_producer_stopped")

    async def send(self, topic: str, value: Any, key: str | None = None) -> None:
        if not self._producer:
            raise RuntimeError("Producer not started")
        key_bytes = key.encode() if key else None
        await self._producer.send_and_wait(topic, value=value, key=key_bytes)

    async def __aenter__(self) -> "KafkaProducer":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()
