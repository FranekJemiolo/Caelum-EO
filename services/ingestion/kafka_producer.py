"""Kafka Producer for GEOINT STAC Ingestion Stream.

Publishes metadata records to the 'geoint-stac-ingest' topic.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import json
from typing import List, Optional
import structlog
from kafka import KafkaProducer
from kafka.errors import KafkaError

from services.ingestion.config import IngestionConfig, STACItemPayload, settings

logger = structlog.get_logger(__name__)


class GEOINTKafkaProducer:
    """Producer for streaming STAC metadata to Kafka with deterministic key partitioning."""

    def __init__(self, config: Optional[IngestionConfig] = None):
        self.config = config or settings
        self.topic = self.config.kafka_topic_stac_ingest
        self.dry_run = self.config.kafka_dry_run
        self._producer: Optional[KafkaProducer] = None
        self._published_history: List[STACItemPayload] = []  # In-memory buffer for dry-run/testing

    @property
    def producer(self) -> KafkaProducer:
        """Lazy connection to Kafka cluster."""
        if self._producer is None and not self.dry_run:
            logger.info("Connecting to Kafka broker", servers=self.config.kafka_bootstrap_servers)
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=self.config.kafka_bootstrap_servers.split(","),
                    client_id=self.config.kafka_client_id,
                    acks=self.config.kafka_acks,
                    retries=self.config.kafka_retries,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None
                )
            except Exception as exc:
                logger.error("Failed to connect to Kafka broker", error=str(exc))
                raise
        return self._producer

    def publish_item(self, payload: STACItemPayload) -> bool:
        """Publish a single STAC item payload to Kafka.

        Uses the MGRS tile or geofence_id as the message key to route items
        from the same geographic cell to the same Kafka partition.
        """
        partition_key = payload.mgrs_tile or payload.geofence_id

        if self.dry_run:
            logger.info(
                "[DRY RUN] Publishing STAC payload to Kafka",
                topic=self.topic,
                key=partition_key,
                item_id=payload.item_id,
                cloud_cover=payload.cloud_cover
            )
            self._published_history.append(payload)
            return True

        try:
            future = self.producer.send(
                topic=self.topic,
                key=partition_key,
                value=payload.model_dump()
            )
            # Asynchronous send with callback handling
            future.add_callback(self._on_send_success, payload.item_id)
            future.add_errback(self._on_send_error, payload.item_id)
            return True
        except KafkaError as err:
            logger.error("Kafka send failed immediately", item_id=payload.item_id, error=str(err))
            return False

    def publish_batch(self, items: List[STACItemPayload]) -> int:
        """Publish a batch of STAC payloads and flush the producer queue."""
        success_count = 0
        for item in items:
            if self.publish_item(item):
                success_count += 1

        self.flush()
        logger.info("Batch publication complete", topic=self.topic, published=success_count, total=len(items))
        return success_count

    def _on_send_success(self, item_id: str, record_metadata):
        logger.debug(
            "STAC item published to Kafka",
            item_id=item_id,
            topic=record_metadata.topic,
            partition=record_metadata.partition,
            offset=record_metadata.offset
        )

    def _on_send_error(self, item_id: str, exc: Exception):
        logger.error("Failed to deliver STAC item to Kafka", item_id=item_id, error=str(exc))

    def flush(self):
        """Flush the internal message queue."""
        if self._producer:
            self._producer.flush()

    def close(self):
        """Close producer connection gracefully."""
        if self._producer:
            logger.info("Closing Kafka producer connection")
            self._producer.flush()
            self._producer.close()
            self._producer = None

    @property
    def published_history(self) -> List[STACItemPayload]:
        """Inspection property for test assertions and validation."""
        return self._published_history
