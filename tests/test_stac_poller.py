"""Unit tests for src/ingestion/stac_poller.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.ingestion.stac_poller import (
    DEFAULT_EASTERN_EUROPE_BBOX,
    REQUIRED_S2_BANDS,
    STACAssetReference,
    STACIngestionWorker,
    STACIngestPayload,
)


def test_stac_payload_models():
    """Verify STAC asset and payload Pydantic models."""
    asset = STACAssetReference(
        band_name="B02",
        href="https://mock/B02.tif",
        media_type="image/tiff",
        title="Blue Band",
    )
    assert asset.band_name == "B02"
    assert asset.href == "https://mock/B02.tif"

    payload = STACIngestPayload(
        item_id="S2A_TEST_001",
        collection="SENTINEL-2",
        datetime="2026-09-27T10:00:00Z",
        bbox=[23.0, 54.0, 23.5, 54.5],
        geometry={"type": "Polygon", "coordinates": []},
        cloud_cover=3.2,
        bands={"B02": asset},
    )
    assert payload.item_id == "S2A_TEST_001"
    dump = payload.model_dump()
    assert dump["cloud_cover"] == 3.2
    assert "B02" in dump["bands"]


def test_stac_worker_initialization():
    """Verify STACIngestionWorker defaults and dry_run configuration."""
    worker = STACIngestionWorker(dry_run=True)
    assert worker.dry_run is True
    assert worker.seen_item_ids == set()
    assert worker.kafka_broker == "localhost:9092"
    assert worker.kafka_topic == "geoint-stac-ingest"


def test_stac_worker_publish_kafka_dry_run():
    """Verify publishing to Kafka in dry_run mode succeeds."""
    worker = STACIngestionWorker(dry_run=True)
    payload = STACIngestPayload(
        item_id="S2A_TEST_002",
        collection="SENTINEL-2",
        datetime="2026-09-27T10:00:00Z",
        bbox=[23.0, 54.0, 23.5, 54.5],
        geometry={"type": "Polygon", "coordinates": []},
        cloud_cover=1.5,
        mgrs_tile="34UFB",
        bands={
            b: STACAssetReference(band_name=b, href=f"https://mock/{b}.tif")
            for b in REQUIRED_S2_BANDS
        },
    )

    success = worker.publish_to_kafka(payload)
    assert success is True


def test_stac_worker_query_mock():
    """Verify querying STAC API with mocked client."""
    worker = STACIngestionWorker(dry_run=True)

    # Mock STAC Item
    mock_item = MagicMock()
    mock_item.id = "S2A_MSIL2A_20260927T100031"
    mock_item.datetime = datetime(2026, 9, 27, 10, 0, 31, tzinfo=timezone.utc)
    mock_item.bbox = [23.1, 54.1, 23.4, 54.4]
    mock_item.geometry = {"type": "Polygon", "coordinates": []}
    mock_item.properties = {"cloudCover": 2.5, "s2:mgrs_tile": "34UFB", "platform": "sentinel-2a"}

    mock_asset = MagicMock()
    mock_asset.href = "https://mock.copernicus.eu/B02.tif"
    mock_asset.media_type = "image/tiff"
    mock_asset.title = "Band B02"
    mock_item.assets = {"B02": mock_asset}

    mock_search = MagicMock()
    mock_search.items.return_value = [mock_item]

    mock_client = MagicMock()
    mock_client.search.return_value = mock_search
    worker._stac_client = mock_client

    start = datetime(2026, 9, 20, tzinfo=timezone.utc)
    end = datetime(2026, 9, 27, tzinfo=timezone.utc)
    results = worker.query_sentinel2_l2a(
        bbox=DEFAULT_EASTERN_EUROPE_BBOX,
        start_time=start,
        end_time=end,
        max_cloud_cover=20.0,
    )

    assert len(results) == 1
    res = results[0]
    assert res.item_id == "S2A_MSIL2A_20260927T100031"
    assert res.cloud_cover == 2.5
    assert len(res.bands) == len(REQUIRED_S2_BANDS)
    assert res.bands["B02"].href == "https://mock.copernicus.eu/B02.tif"


def test_stac_worker_run_polling_cycle():
    """Verify run_polling_cycle queries scenes and records published items."""
    worker = STACIngestionWorker(dry_run=True)

    dummy_payload = STACIngestPayload(
        item_id="S2A_POLL_001",
        collection="SENTINEL-2",
        datetime="2026-09-27T10:00:00Z",
        bbox=[23.0, 54.0, 23.5, 54.5],
        geometry={"type": "Polygon", "coordinates": []},
        cloud_cover=1.0,
        bands={
            b: STACAssetReference(band_name=b, href=f"https://mock/{b}.tif")
            for b in REQUIRED_S2_BANDS
        },
    )

    with patch.object(worker, "query_sentinel2_l2a", return_value=[dummy_payload]):
        count = worker.run_polling_cycle(bbox=DEFAULT_EASTERN_EUROPE_BBOX, days_lookback=3)
        assert count == 1
        assert "S2A_POLL_001" in worker.seen_item_ids

        # Running again with the same item should not republish (deduplication)
        count_duplicate = worker.run_polling_cycle(
            bbox=DEFAULT_EASTERN_EUROPE_BBOX, days_lookback=3
        )
        assert count_duplicate == 0
