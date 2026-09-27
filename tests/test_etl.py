"""Unit tests for Phase 2: ETL Engine, Storage, and Synthetic Data."""

from datetime import datetime, timezone

import numpy as np
import pytest

from scripts.generate_mock_data import create_synthetic_scene_pair, write_scene_geotiffs
from src.etl.cdse_client import PRITHVI_BANDS, CDSEClient
from src.etl.raster_processor import RasterAlignmentProcessor
from src.etl.storage import ObjectStorageManager


@pytest.fixture
def mock_geotiff_dir(tmp_path):
    """Generate temporary synthetic Sentinel-2 GeoTIFFs for testing."""
    t0, t1, scl = create_synthetic_scene_pair(height=64, width=64)
    _ = write_scene_geotiffs(
        output_dir=tmp_path / "mock",
        t0_cube=t0,
        t1_cube=t1,
        scl_mask=scl,
        bbox=[23.10, 54.05, 23.35, 54.25],
    )
    return tmp_path / "mock"


def test_storage_manager_local_numpy_io(tmp_path):
    storage = ObjectStorageManager(fallback_local_dir=str(tmp_path / "storage"))
    dummy_tensor = np.random.uniform(0.0, 1.0, size=(2, 6, 32, 32)).astype(np.float32)

    uri = storage.upload_tensor_array(
        bucket="caelum-interim", key="test_stack.npy", array=dummy_tensor
    )
    assert uri is not None

    downloaded = storage.download_tensor_array(bucket="caelum-interim", key="test_stack.npy")
    assert downloaded.shape == (2, 6, 32, 32)
    assert np.allclose(dummy_tensor, downloaded)


def test_cdse_client_mock_search(mock_geotiff_dir):
    client = CDSEClient(mock_mode=True, mock_data_dir=str(mock_geotiff_dir))
    bbox = [23.10, 54.05, 23.35, 54.25]
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 30, tzinfo=timezone.utc)

    scenes = client.search_scenes(bbox=bbox, start_time=start, end_time=end)

    assert len(scenes) == 2
    t0_scene, t1_scene = scenes[0], scenes[1]
    assert t0_scene.is_mock is True
    assert t1_scene.is_mock is True

    # Validate that all 6 required bands are present
    for b in PRITHVI_BANDS:
        assert b in t0_scene.bands
        assert b in t1_scene.bands


def test_raster_processor_assembly(mock_geotiff_dir):
    client = CDSEClient(mock_mode=True, mock_data_dir=str(mock_geotiff_dir))
    scenes = client.search_scenes(
        bbox=[23.10, 54.05, 23.35, 54.25],
        start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )

    processor = RasterAlignmentProcessor(output_dim=64)
    tensor_pair = processor.co_register_and_create_tensor_pair(
        t0_scene=scenes[0], t1_scene=scenes[1], target_shape=(64, 64)
    )

    # Validate temporal pair shape (2, 6, H, W)
    assert tensor_pair.shape == (2, 6, 64, 64)
    assert tensor_pair.dtype == np.float32
    # Verify normalization range [0.0, 1.0]
    assert 0.0 <= tensor_pair.min() <= tensor_pair.max() <= 1.0


def test_cdse_client_remote_search_mocked():
    """Test CDSEClient search_scenes against mocked pystac-client."""
    from unittest.mock import MagicMock

    client = CDSEClient(mock_mode=False)
    mock_stac_client = MagicMock()
    mock_item = MagicMock()
    mock_item.id = "S2A_LIVE_MOCK"
    mock_item.properties = {"cloudCover": 5.0, "s2:mgrs_tile": "34UFB", "platform": "sentinel-2b"}
    mock_item.datetime = datetime(2026, 9, 27, tzinfo=timezone.utc)
    mock_item.bbox = [23.1, 54.1, 23.4, 54.4]

    mock_asset = MagicMock()
    mock_asset.href = "https://mock.copernicus.eu/B02.tif"
    mock_asset.media_type = "image/tiff"
    mock_item.assets = {"B02": mock_asset, "SCL": MagicMock(href="https://mock/scl.tif")}

    mock_search = MagicMock()
    mock_search.items.return_value = [mock_item]
    mock_stac_client.search.return_value = mock_search
    client._client = mock_stac_client

    scenes = client.search_scenes(
        bbox=[23.1, 54.1, 23.4, 54.4],
        start_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 27, tzinfo=timezone.utc),
    )
    assert len(scenes) == 1
    assert scenes[0].item_id == "S2A_LIVE_MOCK"
    assert scenes[0].is_mock is False


def test_raster_processor_fallback():
    """Verify fallback behavior for unreadable bands."""
    processor = RasterAlignmentProcessor(output_dim=32)
    fallback_band = processor.read_windowed_band(
        band_href="invalid://nonexistent-path.tif",
        bbox=[23.0, 54.0, 23.5, 54.5],
        target_shape=(32, 32),
    )
    assert fallback_band.shape == (32, 32)
