"""Unit tests for GEOINT Kafka producer."""

from services.ingestion.config import IngestionConfig, STACAssetMeta, STACItemPayload
from services.ingestion.kafka_producer import GEOINTKafkaProducer


def test_kafka_producer_dry_run():
    cfg = IngestionConfig(kafka_dry_run=True)
    producer = GEOINTKafkaProducer(config=cfg)

    payload = STACItemPayload(
        item_id="TEST_S2_ITEM",
        collection="SENTINEL-2",
        datetime="2026-09-27T10:00:00Z",
        bbox=[22.8, 53.8, 24.5, 54.7],
        geometry={"type": "Polygon", "coordinates": []},
        cloud_cover=8.0,
        mgrs_tile="34UFB",
        geofence_id="suwalki-gap",
        assets={
            "B02": STACAssetMeta(href="https://copernicus.eu/b02.tif")
        },
        published_at="2026-09-27T10:05:00Z"
    )

    success = producer.publish_item(payload)
    assert success is True
    assert len(producer.published_history) == 1
    assert producer.published_history[0].item_id == "TEST_S2_ITEM"
    assert producer.published_history[0].mgrs_tile == "34UFB"


def test_kafka_producer_batch_publish():
    cfg = IngestionConfig(kafka_dry_run=True)
    producer = GEOINTKafkaProducer(config=cfg)

    items = [
        STACItemPayload(
            item_id=f"ITEM_{i}",
            collection="SENTINEL-2",
            datetime="2026-09-27T10:00:00Z",
            bbox=[22.8, 53.8, 24.5, 54.7],
            geometry={"type": "Polygon", "coordinates": []},
            geofence_id="suwalki-gap",
            mgrs_tile="34UFB",
            assets={},
            published_at="2026-09-27T10:05:00Z"
        )
        for i in range(5)
    ]

    count = producer.publish_batch(items)
    assert count == 5
    assert len(producer.published_history) == 5
