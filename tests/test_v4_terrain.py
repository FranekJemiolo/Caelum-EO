"""Unit tests for Phase 6 / Version 4: 3D DEM Terrain & Viewshed Analytics.

Validates:
- CopernicusDEMClient synthetic topography generation and COG serialization
- Point elevation sampling and Mapbox Terrain-RGB encoding
- Viewshed Line-of-Sight radial raymarching algorithm
- POST /api/v1/analytics/viewshed endpoint integration
"""

import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.analytics.viewshed import calculate_radar_viewshed, compute_viewshed_matrix
from src.api.main import app
from src.etl.dem_client import CopernicusDEMClient


@pytest.fixture
def dem_client(tmp_path):
    """Temporary Copernicus DEM client."""
    return CopernicusDEMClient(local_dir=str(tmp_path / "dem"), mock_mode=True)


def test_dem_synthetic_generation(dem_client):
    """Verify synthetic DEM generation produces valid elevation bounds and transforms."""
    bbox = [23.0, 54.0, 23.3, 54.2]
    elev, transform = dem_client.generate_synthetic_dem(bbox, resolution_deg=0.01)

    assert isinstance(elev, np.ndarray)
    assert elev.ndim == 2
    assert elev.shape[0] > 0 and elev.shape[1] > 0
    assert 50.0 <= float(elev.min()) <= float(elev.max()) <= 400.0
    assert transform is not None


def test_dem_save_cog_and_sample(dem_client, tmp_path):
    """Verify saving elevation model as GeoTIFF and sampling coordinates."""
    bbox = [23.1, 54.1, 23.2, 54.2]
    elev, transform = dem_client.generate_synthetic_dem(bbox, resolution_deg=0.005)
    file_path = dem_client.save_cog(elev, transform, "test_dem.tif", upload_to_storage=False)

    assert os.path.exists(file_path)

    # Sample elevation
    sampled = dem_client.sample_elevation_at_point(23.15, 54.15, dem_path=file_path)
    assert isinstance(sampled, float)
    assert 50.0 <= sampled <= 400.0


def test_dem_encode_terrain_rgb(dem_client):
    """Verify Mapbox Terrain-RGB elevation encoding."""
    test_elev = np.array([[100.0, 250.0], [500.0, 1000.0]], dtype=np.float32)
    rgb = dem_client.encode_terrain_rgb(test_elev)

    assert rgb.shape == (2, 2, 3)
    assert rgb.dtype == np.uint8


def test_viewshed_matrix_computation():
    """Verify raymarching viewshed correctly marks visible and occluded cells."""
    # Synthetic 20x20 grid with a prominent mountain ridge blocking line of sight
    grid = np.ones((25, 25), dtype=np.float32) * 100.0
    # Observer at row 5, col 12 at elev 100m
    # High ridge at row 10 (elev 250m)
    grid[10, :] = 250.0
    # Valley behind ridge at row 15 (elev 90m)
    grid[15, :] = 90.0

    mask = compute_viewshed_matrix(
        dem_array=grid,
        obs_row=5,
        obs_col=12,
        pixel_size_m=30.0,
        obs_height_m=10.0,
        target_height_m=2.0,
        max_radius_m=600.0,
    )

    assert mask.shape == (25, 25)
    # Observer cell itself must be visible
    assert mask[5, 12] == 1
    # Ridge top is visible
    assert mask[10, 12] == 1
    # Valley behind high ridge should be occluded
    assert mask[15, 12] == 0


def test_calculate_radar_viewshed():
    """Verify end-to-end radar viewshed polygon output."""
    feature = calculate_radar_viewshed(
        lon=23.15,
        lat=54.12,
        observer_height=15.0,
        target_height=2.0,
        max_radius_km=5.0,
    )

    assert feature["type"] == "Feature"
    assert "geometry" in feature
    assert feature["geometry"]["type"] in ["Polygon", "MultiPolygon"]
    assert "properties" in feature
    props = feature["properties"]
    assert props["sensor_max_range_km"] == 5.0
    assert props["visible_area_sq_km"] > 0
    assert 0.0 <= props["coverage_percentage"] <= 100.0


def test_api_viewshed_endpoint():
    """Test POST /api/v1/analytics/viewshed with JWT authentication."""
    client = TestClient(app)

    # 1. Login as analyst
    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Call viewshed calculation
    payload = {
        "lon": 23.15,
        "lat": 54.12,
        "observer_height": 20.0,
        "max_radius_km": 6.0,
    }
    resp = client.post("/api/v1/analytics/viewshed", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "Feature"
    assert "coordinates" in data["geometry"]
    assert data["properties"]["antenna_height_m"] == 20.0
