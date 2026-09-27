"""STAC Ingestion Firehose Poller Worker.

Coordinates polling across defined surveillance geofences and pushes
discovered Copernicus metadata to Kafka.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Set
import click
import structlog

from services.ingestion.config import IngestionConfig, settings
from services.ingestion.cdse_stac_client import CDSEStacClient
from services.ingestion.kafka_producer import GEOINTKafkaProducer

logger = structlog.get_logger(__name__)


class STACIngestionWorker:
    """Orchestrates recurring STAC querying and Kafka publishing."""

    def __init__(
        self,
        config: Optional[IngestionConfig] = None,
        stac_client: Optional[CDSEStacClient] = None,
        kafka_producer: Optional[GEOINTKafkaProducer] = None
    ):
        self.config = config or settings
        self.stac_client = stac_client or CDSEStacClient(self.config)
        self.kafka_producer = kafka_producer or GEOINTKafkaProducer(self.config)
        self.seen_item_ids: Set[str] = set()

    def run_cycle(self, target_geofence_id: Optional[str] = None) -> int:
        """Run a single ingestion cycle across all or a selected geofence.

        Returns:
            Total count of newly published items.
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=self.config.lookback_days)

        active_geofences = self.config.geofences
        if target_geofence_id:
            active_geofences = [g for g in active_geofences if g.id == target_geofence_id]
            if not active_geofences:
                logger.error("Specified geofence not found in configuration", geofence_id=target_geofence_id)
                return 0

        total_published = 0
        logger.info(
            "Starting STAC ingestion cycle",
            geofences_count=len(active_geofences),
            window_start=start_time.isoformat(),
            window_end=now.isoformat()
        )

        for geofence in active_geofences:
            try:
                items = self.stac_client.search_geofence(
                    geofence=geofence,
                    start_time=start_time,
                    end_time=now,
                    max_cloud_cover=self.config.default_cloud_cover_max,
                    limit=self.config.max_items_per_query
                )

                # Deduplicate against previously published items in this worker session
                new_items = [item for item in items if item.item_id not in self.seen_item_ids]
                logger.info(
                    "Geofence query evaluated",
                    geofence_id=geofence.id,
                    total_found=len(items),
                    new_unseen=len(new_items)
                )

                if new_items:
                    published = self.kafka_producer.publish_batch(new_items)
                    total_published += published
                    for item in new_items:
                        self.seen_item_ids.add(item.item_id)

            except Exception as exc:
                logger.exception("Failed processing geofence", geofence_id=geofence.id, error=str(exc))
                continue

        logger.info("Ingestion cycle concluded", total_new_published=total_published)
        return total_published

    def run_loop(self):
        """Continuously run polling cycles on configured interval."""
        logger.info(
            "Starting continuous STAC ingestion daemon",
            poll_interval_seconds=self.config.poll_interval_seconds
        )
        try:
            while True:
                self.run_cycle()
                logger.info("Sleeping until next polling cycle", seconds=self.config.poll_interval_seconds)
                time.sleep(self.config.poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Ingestion daemon stopped by user")
        finally:
            self.kafka_producer.close()


@click.command()
@click.option("--once", is_flag=True, default=False, help="Run single poll cycle and exit immediately.")
@click.option("--geofence", type=str, default=None, help="Filter to specific geofence ID.")
@click.option("--dry-run", is_flag=True, default=False, help="Skip live Kafka send and log payloads.")
def cli(once: bool, geofence: Optional[str], dry_run: bool):
    """Caelum-EO STAC Ingestion CLI Worker."""
    cfg = settings
    if dry_run:
        cfg.kafka_dry_run = True

    worker = STACIngestionWorker(config=cfg)

    if once:
        published = worker.run_cycle(target_geofence_id=geofence)
        worker.kafka_producer.close()
        sys.exit(0 if published >= 0 else 1)
    else:
        worker.run_loop()


if __name__ == "__main__":
    cli()
