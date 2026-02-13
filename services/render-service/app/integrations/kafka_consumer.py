"""
Kafka / Redpanda consumer for render-service.

Listens on ``video.events`` for ``script.generated`` events and creates
render jobs automatically.

Includes:
  - Deserialisation via ``DomainEvent.from_kafka_value()``
  - Basic retry with exponential backoff (3 attempts)
  - DLQ fallback on permanent failure
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC, KAFKA_CONSUMER_GROUP
from contracts import DomainEvent

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0


async def start_consumer(db_session_factory) -> None:
    """Start the Kafka consumer loop. Runs as a background task."""
    try:
        from aiokafka import AIOKafkaConsumer
    except ImportError:
        logger.warning("aiokafka not available – consumer disabled")
        return

    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )

    try:
        await consumer.start()
        logger.info("Kafka consumer started on topic: %s", KAFKA_TOPIC)

        async for msg in consumer:
            await _process_message_with_retry(msg, db_session_factory)

    except asyncio.CancelledError:
        logger.info("Kafka consumer shutting down")
    except Exception:
        logger.exception("Kafka consumer fatal error")
    finally:
        await consumer.stop()


async def _process_message_with_retry(msg, db_session_factory) -> None:
    """Process a Kafka message with retry + DLQ fallback."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            event = DomainEvent.from_kafka_value(msg.value)

            if event.event_type == "script.generated":
                logger.info(
                    "Received script.generated event: %s (attempt %d)",
                    event.event_id,
                    attempt,
                )
                await _handle_script_generated(event, db_session_factory)
            else:
                logger.debug("Ignoring event type: %s", event.event_type)

            return  # Success – exit retry loop

        except Exception:
            logger.warning(
                "Error processing message (attempt %d/%d)",
                attempt,
                MAX_RETRIES,
                exc_info=True,
            )
            if attempt < MAX_RETRIES:
                backoff = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

    # All retries exhausted → send to DLQ
    logger.error("Max retries exhausted – sending to DLQ")
    try:
        from common.kafka import publish_to_dlq

        await publish_to_dlq(
            original_topic=KAFKA_TOPIC,
            raw_value=msg.value,
            error="Max retries exhausted in render-service consumer",
            retry_count=MAX_RETRIES,
        )
    except Exception:
        logger.exception("Failed to publish to DLQ – message lost")


async def _handle_script_generated(event: DomainEvent, db_session_factory) -> None:
    """Handle a ``script.generated`` event by creating a render job."""
    from app.services.render_service import RenderService

    payload = event.payload
    db = db_session_factory()
    try:
        svc = RenderService(db)
        await svc.create_render_from_script_event(payload)
    finally:
        db.close()
