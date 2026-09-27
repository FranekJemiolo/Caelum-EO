"""Unit tests for Ingestion configuration and schemas."""

import pytest
from services.ingestion.config import Geofence, STACAssetMeta, STACItemPayload, IngestionConfig


def test_geofence_initialization():
    zone = Geofence(
        id="test-zone",
        name="Test Corridor",
        bbox=[20.0, 50.0, 21.0, 51.0],
        description="Testing zone"
    )
    assert zone.id == "test-zone"
    assert len(zone.bbox) == 4
    assert zone.bbox[0] == 20.0


def test_stac_item_payload_serialization():
    payload = STACItemPayload(
        item_id="S2A_TEST_001",
        collection="SENTINEL-2",
        datetime="2026-09-27T12:00:00Z",
        bbox=[20.0, 50.0, 21.0, 51.0],
        geometry={"type": "Polygon", "coordinates": []},
        cloud_cover=12.5,
        platform="sentinel-2a",
        mgrs_tile="34UDA",
        geofence_id="test-zone",
        assets={
            "B02": STACAssetMeta(href="https://data.copernicus.eu/b02.tif", type="image/tiff")
        },
        published_at="2026-09-27T12:05:00Z"
    )
    dumped = payload.model_dump()
    assert dumped["item_id"] == "S2A_TEST_001"
    assert dumped["cloud_cover"] == 12.5
    assert dumped["mgrs_tile"] == "34UDA"
    assert "B02" in dumped["assets"]


def test_ingestion_config_defaults():
    cfg = IngestionConfig()
    assert cfg.kafka_topic_stac_ingest == "geoint-stac-ingest"
    assert "B02" in cfg.sentinel2_bands
    assert "B12" in cfg.sentinel2_bands
    assert len(cfg.geofences) >= 3
