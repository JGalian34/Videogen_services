"""
Shared Kafka / Redpanda helpers.

Provides:
  - ``publish_event()``: serialise a ``DomainEvent`` and send it to a topic.
  - ``publish_to_dlq()``: send a failed raw message to ``dlq.events``.
  - ``start_kafka_producer()`` / ``stop_kafka_producer()``: lifecycle hooks.

All services should use these helpers instead of building their own
AIOKafkaProducer boilerplate.
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.events import DomainEvent
from common.config import KAFKA_BOOTSTRAP_SERVERS
from common.middleware.correlation import get_correlation_id

logger = logging.getLogger(__name__)

DLQ_TOPIC = "dlq.events"

# ── Singleton producer ──────────────────────────────────────────────
_producer = None


async def start_kafka_producer() -> None:
    """Start the singleton Kafka producer. Call from app lifespan startup."""
    global _producer
    if _producer is not None:
        return
    try:
        from aiokafka import AIOKafkaProducer

        _producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        await _producer.start()
        logger.info("Kafka producer started (bootstrap: %s)", KAFKA_BOOTSTRAP_SERVERS)
    except Exception:
        logger.warning("Kafka producer could not start – events will be logged locally", exc_info=True)
        _producer = None


async def stop_kafka_producer() -> None:
    """Stop the singleton Kafka producer. Call from app lifespan shutdown."""
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer stopped")


async def _get_producer():
    """Return the singleton producer, starting it if needed (lazy fallback)."""
    global _producer
    if _producer is None:
        await start_kafka_producer()
    return _producer


# ── Publish ─────────────────────────────────────────────────────────


async def publish_event(
    *,
    topic: str,
    event_type: str,
    payload: dict[str, Any],
    key: str | None = None,
    correlation_id: str | None = None,
) -> DomainEvent:
    """Build a ``DomainEvent`` envelope and publish it to *topic*.

    Returns the built ``DomainEvent`` (useful for logging / tests).
    Falls back to local logging if the broker is unreachable.
    """
    event = DomainEvent(
        event_type=event_type,
        correlation_id=correlation_id or get_correlation_id(),
        payload=payload,
    )

    producer = await _get_producer()
    if producer is None:
        logger.warning(
            "Kafka unavailable – event logged locally: %s %s",
            event.event_type,
            event.event_id,
        )
        return event

    try:
        await producer.send_and_wait(
            topic,
            value=event.to_kafka_value(),
            key=(key or event.event_id).encode("utf-8"),
        )
        logger.info(
            "Event published: %s [%s] → %s",
            event.event_type,
            event.event_id,
            topic,
        )
    except Exception:
        logger.warning(
            "Kafka send failed – event logged locally: %s %s",
            event.event_type,
            event.event_id,
            exc_info=True,
        )

    return event


# ── DLQ ─────────────────────────────────────────────────────────────


async def publish_to_dlq(
    *,
    original_topic: str,
    raw_value: bytes,
    error: str,
    retry_count: int = 0,
) -> None:
    """Send a failed message to the dead-letter queue topic."""
    dlq_payload = {
        "original_topic": original_topic,
        "raw_value": raw_value.decode("utf-8", errors="replace"),
        "error": str(error),
        "retry_count": retry_count,
    }

    producer = await _get_producer()
    if producer is None:
        logger.error("Cannot publish to DLQ – Kafka unavailable. Error: %s", error)
        return

    try:
        event = DomainEvent(
            event_type="dlq.message_failed",
            correlation_id=get_correlation_id(),
            payload=dlq_payload,
        )
        await producer.send_and_wait(
            DLQ_TOPIC,
            value=event.to_kafka_value(),
            key=event.event_id.encode("utf-8"),
        )
        logger.warning("Message sent to DLQ: %s", error)
    except Exception:
        logger.error("Failed to publish to DLQ – message lost: %s", error, exc_info=True)
