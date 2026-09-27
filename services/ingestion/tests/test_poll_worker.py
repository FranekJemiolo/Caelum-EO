"""Unit tests for STAC polling worker orchestration."""

from unittest.mock import MagicMock

from services.ingestion.config import IngestionConfig, STACItemPayload
from services.ingestion.poll_worker import STACIngestionWorker


def test_poll_worker_deduplication():
    cfg = IngestionConfig(kafka_dry_run=True)
    mock_stac = MagicMock()
    mock_producer = MagicMock()

    item_1 = STACItemPayload(
        item_id="SCENE_AAA",
        collection="SENTINEL-2",
        datetime="2026-09-27T10:00:00Z",
        bbox=[22.8, 53.8, 24.5, 54.7],
        geometry={},
        geofence_id="suwalki-gap",
        assets={},
        published_at="2026-09-27T10:00:00Z",
    )

    mock_stac.search_geofence.return_value = [item_1]
    mock_producer.publish_batch.return_value = 1

    worker = STACIngestionWorker(config=cfg, stac_client=mock_stac, kafka_producer=mock_producer)

    # First cycle - item should be published
    published_cycle_1 = worker.run_cycle(target_geofence_id="suwalki-gap")
    assert published_cycle_1 == 1
    assert "SCENE_AAA" in worker.seen_item_ids
    assert mock_producer.publish_batch.call_count == 1

    # Second cycle - same item returned from STAC query, should be skipped
    published_cycle_2 = worker.run_cycle(target_geofence_id="suwalki-gap")
    assert published_cycle_2 == 0
    # publish_batch should NOT have been called again
    assert mock_producer.publish_batch.call_count == 1
