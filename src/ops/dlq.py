"""Kafka Dead Letter Queue (DLQ) Handler for Project Caelum-EO.

Ensures corrupted STAC imagery, malformed payloads, and Out-of-Memory (OOM) exceptions
are captured with full stack traces and routed to a dedicated DLQ topic ('caelum.dlq')
without terminating worker processes or silently dropping geographic intelligence tiles.
"""

import json
import os
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from src.ops.metrics import DLQ_MESSAGES_TOTAL

logger = structlog.get_logger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "caelum.dlq")


class DeadLetterQueue:
    """Manages Dead Letter Queue dispatching and local audit trail."""

    def __init__(
        self,
        kafka_broker: Optional[str] = None,
        dlq_topic: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.kafka_broker = kafka_broker or KAFKA_BOOTSTRAP_SERVERS
        self.dlq_topic = dlq_topic or DEFAULT_DLQ_TOPIC
        self.dry_run = dry_run or os.getenv("CAELUM_MOCK_INGEST", "false").lower() == "true"
        self._producer = None
        self._in_memory_dlq: List[Dict[str, Any]] = []

    @property
    def producer(self):
        if self._producer is None and not self.dry_run:
            try:
                from kafka import KafkaProducer

                self._producer = KafkaProducer(
                    bootstrap_servers=self.kafka_broker.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    acks="all",
                    retries=3,
                    request_timeout_ms=5000,
                )
            except Exception as exc:
                logger.warning(
                    "Kafka DLQ producer connection failed; operating with in-memory DLQ store",
                    error=str(exc),
                )
                self._producer = None
        return self._producer

    def send_to_dlq(
        self,
        failed_topic: str,
        original_payload: Any,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Serialize failed processing state and route to Kafka Dead Letter Queue.

        Args:
            failed_topic: Name of Kafka topic where processing originated.
            original_payload: The raw message or parsed dictionary that failed.
            error: The captured Exception.
            context: Additional debugging metadata (e.g. tile_id, bbox, worker_name).

        Returns:
            The structured DLQ record.
        """
        error_type = type(error).__name__
        error_msg = str(error)
        stack = traceback.format_exc()
        now_iso = datetime.now(timezone.utc).isoformat()
        dlq_id = str(uuid.uuid4())

        dlq_record = {
            "dlq_id": dlq_id,
            "timestamp": now_iso,
            "failed_topic": failed_topic,
            "error_type": error_type,
            "error_message": error_msg,
            "stack_trace": stack,
            "context": context or {},
            "original_payload": original_payload
            if isinstance(original_payload, (dict, list, str, int, float, bool))
            else str(original_payload),
        }

        # 1. Update Prometheus fault metrics
        try:
            DLQ_MESSAGES_TOTAL.labels(failed_topic=failed_topic, error_type=error_type).inc()
        except Exception:
            pass

        # 2. Log structured warning
        logger.warning(
            "Message routed to Dead Letter Queue (DLQ)",
            dlq_id=dlq_id,
            failed_topic=failed_topic,
            error_type=error_type,
            error_message=error_msg,
            context=context,
        )

        # 3. Publish to Kafka DLQ Topic if connected
        producer = self.producer
        if producer is not None:
            try:
                future = producer.send(
                    topic=self.dlq_topic,
                    key=dlq_id,
                    value=dlq_record,
                )
                future.get(timeout=5)
            except Exception as exc:
                logger.error("Failed publishing to Kafka DLQ topic", error=str(exc))

        # 4. Save in memory for local queries / fallback
        self._in_memory_dlq.append(dlq_record)
        return dlq_record

    def get_dlq_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent DLQ events from in-memory audit store."""
        return list(reversed(self._in_memory_dlq))[:limit]

    def clear(self) -> None:
        """Clear in-memory buffer (useful for unit testing)."""
        self._in_memory_dlq.clear()


dlq_manager = DeadLetterQueue()
