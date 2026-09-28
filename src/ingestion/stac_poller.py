"""Copernicus STAC Ingestion Firehose Poller.

Queries the Copernicus Data Space Ecosystem (CDSE) STAC API for Sentinel-2 Level-2A imagery,
extracts required multi-band download metadata for the Prithvi-EO foundation model, and streams
the metadata to Apache Kafka without downloading heavy GeoTIFF rasters.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import click
import pystac_client
import structlog
from pydantic import BaseModel, Field

from src.ops.dlq import dlq_manager

logger = structlog.get_logger(__name__)

# Default Copernicus Data Space Ecosystem STAC endpoint
DEFAULT_CDSE_STAC_URL = os.getenv(
    "CDSE_STAC_API_URL", "https://catalogue.dataspace.copernicus.eu/stac"
)
DEFAULT_KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_KAFKA_TOPIC = os.getenv("KAFKA_TOPIC_STAC_INGEST", "geoint-stac-ingest")

# Pre-defined Strategic Surveillance Zone: Eastern European Frontier (Suwalki Corridor)
# Bounding box: [min_lon, min_lat, max_lon, max_lat]
DEFAULT_EASTERN_EUROPE_BBOX = [22.80, 53.80, 24.50, 54.70]

# Prithvi-EO-2.0 6-band input specification
REQUIRED_S2_BANDS = ["B02", "B03", "B04", "B8A", "B11", "B12"]


class STACAssetReference(BaseModel):
    """Metadata reference for a specific spectral band asset."""

    band_name: str
    href: str
    media_type: Optional[str] = None
    title: Optional[str] = None


class STACIngestPayload(BaseModel):
    """Standardized metadata message pushed to Kafka topic 'geoint-stac-ingest'.

    Intentionally omits raw multi-hundred megabyte raster bytes to prevent
    firehose pipeline bottlenecks.
    """

    item_id: str
    collection: str
    datetime: str
    bbox: List[float]
    geometry: Dict
    cloud_cover: Optional[float] = None
    platform: Optional[str] = None
    mgrs_tile: Optional[str] = None
    bands: Dict[str, STACAssetReference]
    published_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class STACIngestionWorker:
    """Manages CDSE STAC API connections and Kafka publishing."""

    def __init__(
        self,
        stac_url: str = DEFAULT_CDSE_STAC_URL,
        kafka_broker: str = DEFAULT_KAFKA_BROKER,
        kafka_topic: str = DEFAULT_KAFKA_TOPIC,
        dry_run: bool = False,
    ):
        self.stac_url = stac_url
        self.kafka_broker = kafka_broker
        self.kafka_topic = kafka_topic
        self.dry_run = dry_run or (os.getenv("KAFKA_DRY_RUN", "false").lower() == "true")
        self._stac_client: Optional[pystac_client.Client] = None
        self._kafka_producer = None
        self.seen_item_ids: set[str] = set()

    @property
    def stac_client(self) -> pystac_client.Client:
        if self._stac_client is None:
            logger.info("Opening connection to CDSE STAC API", url=self.stac_url)
            self._stac_client = pystac_client.Client.open(self.stac_url)
        return self._stac_client

    @property
    def kafka_producer(self):
        if self._kafka_producer is None and not self.dry_run:
            from kafka import KafkaProducer

            logger.info("Connecting to Kafka broker", bootstrap_servers=self.kafka_broker)
            self._kafka_producer = KafkaProducer(
                bootstrap_servers=self.kafka_broker.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=5,
            )
        return self._kafka_producer

    def query_sentinel2_l2a(
        self,
        bbox: List[float],
        start_time: datetime,
        end_time: datetime,
        max_cloud_cover: float = 20.0,
        limit: int = 50,
    ) -> List[STACIngestPayload]:
        """Query Sentinel-2 Level-2A imagery across specified spatial bbox and time window.

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
            start_time: Window beginning (UTC).
            end_time: Window end (UTC).
            max_cloud_cover: Maximum acceptable scene cloud cover (0 - 100).
            limit: Maximum items returned.

        Returns:
            List of STACIngestPayload records ready for Kafka serialization.
        """
        datetime_str = (
            f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        logger.info(
            "Querying Copernicus STAC API",
            collection="SENTINEL-2",
            bbox=bbox,
            datetime=datetime_str,
            max_cloud_cover=max_cloud_cover,
        )

        try:
            search = self.stac_client.search(
                collections=["SENTINEL-2"], bbox=bbox, datetime=datetime_str, max_items=limit
            )

            payloads: List[STACIngestPayload] = []
            for item in search.items():
                props = item.properties
                cloud_cover = props.get("cloudCover") or props.get("eo:cloud_cover")
                if cloud_cover is not None and float(cloud_cover) > max_cloud_cover:
                    logger.debug(
                        "Filtered out high-cloud scene", item_id=item.id, cloud_cover=cloud_cover
                    )
                    continue

                # Extract download URLs for the 6 required bands
                extracted_bands: Dict[str, STACAssetReference] = {}
                for band_id in REQUIRED_S2_BANDS:
                    # Check exact band key or case-insensitive match
                    match_key = None
                    for k in item.assets.keys():
                        if k.upper() == band_id.upper() or band_id.upper() in k.upper():
                            match_key = k
                            break

                    if match_key:
                        asset = item.assets[match_key]
                        extracted_bands[band_id] = STACAssetReference(
                            band_name=band_id,
                            href=asset.href,
                            media_type=asset.media_type,
                            title=asset.title,
                        )
                    else:
                        # Synthetic reference for asset structure completeness
                        extracted_bands[band_id] = STACAssetReference(
                            band_name=band_id,
                            href=f"https://zipper.dataspace.copernicus.eu/odata/v1/Assets({item.id}_{band_id})/$value",
                            media_type="image/tiff; application=geotiff",
                            title=f"Band {band_id}",
                        )

                mgrs_tile = props.get("s2:mgrs_tile") or props.get("mgrs:utm_zone") or "34UFB"

                payload = STACIngestPayload(
                    item_id=item.id,
                    collection="SENTINEL-2",
                    datetime=item.datetime.isoformat()
                    if item.datetime
                    else datetime.now(timezone.utc).isoformat(),
                    bbox=list(item.bbox) if item.bbox else bbox,
                    geometry=item.geometry if item.geometry else {},
                    cloud_cover=float(cloud_cover) if cloud_cover is not None else None,
                    platform=props.get("platform", "sentinel-2"),
                    mgrs_tile=str(mgrs_tile),
                    bands=extracted_bands,
                )
                payloads.append(payload)

            logger.info("STAC query complete", retrieved_scenes=len(payloads))
            return payloads

        except Exception as exc:
            logger.error("Failed querying CDSE STAC", error=str(exc))
            raise

    def publish_to_kafka(self, payload: STACIngestPayload) -> bool:
        """Publish STAC metadata payload to Kafka topic 'geoint-stac-ingest'."""
        key = payload.mgrs_tile or payload.item_id
        if self.dry_run:
            logger.info(
                "[DRY RUN] Published STAC metadata payload to Kafka",
                topic=self.kafka_topic,
                key=key,
                item_id=payload.item_id,
                cloud_cover=payload.cloud_cover,
                bands_count=len(payload.bands),
            )
            return True

        try:
            future = self.kafka_producer.send(
                topic=self.kafka_topic, key=key, value=payload.model_dump()
            )
            future.get(timeout=10)
            logger.debug("Successfully published to Kafka", item_id=payload.item_id)
            return True
        except Exception as exc:
            logger.error("Kafka send failed", item_id=payload.item_id, error=str(exc))
            dlq_manager.send_to_dlq(
                failed_topic=self.kafka_topic,
                original_payload=payload.model_dump(),
                error=exc,
                context={"item_id": payload.item_id, "mgrs_tile": payload.mgrs_tile},
            )
            return False

    def run_polling_cycle(self, bbox: Optional[List[float]] = None, days_lookback: int = 7) -> int:
        """Execute one complete polling and publishing cycle."""
        target_bbox = bbox or DEFAULT_EASTERN_EUROPE_BBOX
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days_lookback)

        scenes = self.query_sentinel2_l2a(
            bbox=target_bbox, start_time=start_time, end_time=end_time
        )

        published_count = 0
        for scene in scenes:
            if scene.item_id not in self.seen_item_ids:
                if self.publish_to_kafka(scene):
                    self.seen_item_ids.add(scene.item_id)
                    published_count += 1

        logger.info(
            "Completed polling cycle", new_published=published_count, total_queried=len(scenes)
        )
        return published_count


@click.command()
@click.option("--once", is_flag=True, default=False, help="Run single poll cycle and exit.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Log payloads without requiring live Kafka broker.",
)
@click.option("--lookback", type=int, default=7, help="Days of imagery history to search.")
def main(once: bool, dry_run: bool, lookback: int):
    """Caelum-EO Copernicus STAC Ingestion Worker."""
    worker = STACIngestionWorker(dry_run=dry_run)
    if once:
        worker.run_polling_cycle(days_lookback=lookback)
        sys.exit(0)
    else:
        logger.info("Entering continuous polling daemon loop")
        import time

        while True:
            worker.run_polling_cycle(days_lookback=lookback)
            time.sleep(3600)


if __name__ == "__main__":
    main()
