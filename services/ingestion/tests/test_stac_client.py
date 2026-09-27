"""Unit tests for CDSE STAC API client."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from services.ingestion.config import Geofence, IngestionConfig
from services.ingestion.cdse_stac_client import CDSEStacClient


class MockSTACAsset:
    def __init__(self, href: str, media_type: str = "image/tiff"):
        self.href = href
        self.media_type = media_type
        self.title = "Mock Asset"


class MockSTACItem:
    def __init__(self, item_id: str, cloud_cover: float, collection_id: str = "SENTINEL-2"):
        self.id = item_id
        self.collection_id = collection_id
        self.datetime = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        self.bbox = [22.8, 53.8, 24.5, 54.7]
        self.geometry = {"type": "Polygon", "coordinates": [[[22.8, 53.8], [24.5, 53.8], [24.5, 54.7], [22.8, 54.7], [22.8, 53.8]]]}
        self.properties = {
            "cloudCover": cloud_cover,
            "platform": "sentinel-2b",
            "constellation": "sentinel-2",
            "s2:mgrs_tile": "34UFB"
        }
        self.assets = {
            "B02": MockSTACAsset("https://copernicus.eu/b02.tif"),
            "B03": MockSTACAsset("https://copernicus.eu/b03.tif"),
            "B04": MockSTACAsset("https://copernicus.eu/b04.tif"),
            "B8A": MockSTACAsset("https://copernicus.eu/b8a.tif"),
            "B11": MockSTACAsset("https://copernicus.eu/b11.tif"),
            "B12": MockSTACAsset("https://copernicus.eu/b12.tif"),
            "TCI": MockSTACAsset("https://copernicus.eu/tci.tif"),  # Should not be in required bands
        }


@pytest.fixture
def mock_geofence():
    return Geofence(
        id="suwalki-test",
        name="Suwalki Test",
        bbox=[22.8, 53.8, 24.5, 54.7]
    )


def test_stac_client_filters_high_cloud_cover(mock_geofence):
    client = CDSEStacClient()
    mock_pystac = MagicMock()

    # Two items: one below threshold (10%), one above threshold (85%)
    item_clear = MockSTACItem("S2_CLEAR", cloud_cover=10.0)
    item_cloudy = MockSTACItem("S2_CLOUDY", cloud_cover=85.0)

    mock_search = MagicMock()
    mock_search.items.return_value = [item_clear, item_cloudy]
    mock_pystac.search.return_value = mock_search

    with patch.object(CDSEStacClient, "client", new=mock_pystac):
        results = client.search_geofence(
            geofence=mock_geofence,
            start_time=datetime(2026, 9, 20, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 27, tzinfo=timezone.utc),
            max_cloud_cover=20.0
        )

        assert len(results) == 1
        assert results[0].item_id == "S2_CLEAR"
        assert results[0].cloud_cover == 10.0
        assert results[0].mgrs_tile == "34UFB"
        assert "B02" in results[0].assets
        assert "B12" in results[0].assets


def test_stac_client_extracts_required_bands(mock_geofence):
    client = CDSEStacClient()
    mock_pystac = MagicMock()

    item = MockSTACItem("S2_TEST_BANDS", cloud_cover=5.0)
    mock_search = MagicMock()
    mock_search.items.return_value = [item]
    mock_pystac.search.return_value = mock_search

    with patch.object(CDSEStacClient, "client", new=mock_pystac):
        results = client.search_geofence(
            geofence=mock_geofence,
            start_time=datetime(2026, 9, 20, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 27, tzinfo=timezone.utc)
        )

        payload = results[0]
        # Verify 6 bands for Prithvi foundation model
        for band in ["B02", "B03", "B04", "B8A", "B11", "B12"]:
            assert band in payload.assets
            assert payload.assets[band].href.endswith(f"{band.lower()}.tif")
