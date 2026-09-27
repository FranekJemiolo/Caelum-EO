"""Unit tests for Phase 2: ETL Engine, Storage, and Synthetic Data."""

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pytest

from scripts.generate_mock_data import create_synthetic_scene_pair, write_scene_geotiffs
from src.etl.storage import ObjectStorageManager
from src.etl.cdse_client import CDSEClient, PRITHVI_BANDS
from src.etl.raster_processor import RasterAlignmentProcessor


@pytest.fixture
def mock_geotiff_dir(tmp_path):
    """Generate temporary synthetic Sentinel-2 GeoTIFFs for testing."""
    t0, t1, scl = create_synthetic_scene_pair(height=64, width=64)
    manifest = write_scene_geotiffs(
        output_dir=tmp_path / "mock",
        t0_cube=t0,
        t1_cube=t1,
        scl_mask=scl,
        bbox=[23.10, 54.05, 23.35, 54.25]
    )
    return tmp_path / "mock"


def test_storage_manager_local_numpy_io(tmp_path):
    storage = ObjectStorageManager(fallback_local_dir=str(tmp_path / "storage"))
    dummy_tensor = np.random.uniform(0.0, 1.0, size=(2, 6, 32, 32)).astype(np.float32)

    uri = storage.upload_tensor_array(
        bucket="caelum-interim",
        key="test_stack.npy",
        array=dummy_tensor
    )
    assert uri is not None

    downloaded = storage.download_tensor_array(
        bucket="caelum-interim",
        key="test_stack.npy"
    )
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
        end_time=datetime(2026, 9, 30, tzinfo=timezone.utc)
    )

    processor = RasterAlignmentProcessor(output_dim=64)
    tensor_pair = processor.co_register_and_create_tensor_pair(
        t0_scene=scenes[0],
        t1_scene=scenes[1],
        target_shape=(64, 64)
    )

    # Validate temporal pair shape (2, 6, H, W)
    assert tensor_pair.shape == (2, 6, 64, 64)
    assert tensor_pair.dtype == np.float32
    # Verify normalization range [0.0, 1.0]
    assert 0.0 <= tensor_pair.min() <= tensor_pair.max() <= 1.0
