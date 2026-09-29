"""Unit tests for Phase 6 / Version 4: Construction Velocity & Pattern of Life (PoL) Analytics.

Validates:
- SQL window function result aggregation and first-derivative expansion rate calculations
- Deterministic synthetic multi-temporal timeline modeling
- REST endpoint GET /api/v1/analytics/velocity with filters and authentication
- CLI runner for terminal operator assessments
"""

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.velocity import VelocityAnalyticsEngine, main


@pytest.fixture
def mock_window_rows():
    """Sample output from PostGIS window function query."""
    return [
        {
            "classification": "LOGISTICS_DEPOT",
            "detection_timestamp": "2026-04-01T00:00:00Z",
            "area_m2": 1500.0,
            "cumulative_area": 1500.0,
            "prev_timestamp": None,
            "delta_days": 1.0,
        },
        {
            "classification": "LOGISTICS_DEPOT",
            "detection_timestamp": "2026-04-15T00:00:00Z",
            "area_m2": 3000.0,
            "cumulative_area": 4500.0,
            "prev_timestamp": "2026-04-01T00:00:00Z",
            "delta_days": 14.0,
        },
        {
            "classification": "RADAR_DOME",
            "detection_timestamp": "2026-05-01T00:00:00Z",
            "area_m2": 450.0,
            "cumulative_area": 450.0,
            "prev_timestamp": None,
            "delta_days": 1.0,
        },
    ]


def test_velocity_format_query_results(mock_window_rows):
    """Verify first-derivative expansion calculation from window query rows."""
    engine = VelocityAnalyticsEngine()
    result = engine._format_query_results(mock_window_rows, zone_id="suwalki_corridor")

    assert result.zone_id == "suwalki_corridor"
    assert result.total_area_sq_m == 4950.0  # 4500 (logistics) + 450 (radar)
    assert len(result.classes) == 2

    # Check Logistics Depot
    logistics = next(c for c in result.classes if c.classification == "LOGISTICS_DEPOT")
    assert logistics.current_area_sq_m == 4500.0
    assert logistics.total_detections == 2
    assert len(logistics.timeline) == 2
    # Second data point rate: 3000 m2 / 14 days = ~214.29 m2/day
    assert 210.0 <= logistics.timeline[1].expansion_rate_sq_m_per_day <= 220.0


def test_velocity_synthetic_modeling():
    """Verify deterministic high-fidelity 6-month Pattern of Life modeling."""
    engine = VelocityAnalyticsEngine()
    result = engine._generate_synthetic_velocity(zone_id="gotland_deep", months_lookback=6)

    assert result.zone_id == "gotland_deep"
    assert result.total_area_sq_m > 10000.0
    assert result.mean_velocity_sq_m_per_day > 0.0
    assert len(result.classes) >= 4

    for c in result.classes:
        assert c.current_area_sq_m > 0
        assert c.expansion_rate_sq_m_per_day > 0
        assert len(c.timeline) > 5
        # Ensure monotonic growth in cumulative footprint
        cum_areas = [p.cumulative_area_sq_m for p in c.timeline]
        assert cum_areas == sorted(cum_areas)


def test_velocity_api_endpoint():
    """Verify GET /api/v1/analytics/velocity endpoint returns valid response."""
    client = TestClient(app)

    # Authenticate as analyst
    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Request velocity analytics
    resp = client.get(
        "/api/v1/analytics/velocity?zone_id=suwalki_corridor&months_lookback=6",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["zone_id"] == "suwalki_corridor"
    assert "total_area_sq_m" in data
    assert "mean_velocity_sq_m_per_day" in data
    assert "classes" in data
    assert len(data["classes"]) > 0

    first_class = data["classes"][0]
    assert "classification" in first_class
    assert "current_area_sq_m" in first_class
    assert "expansion_rate_sq_m_per_day" in first_class
    assert "timeline" in first_class


def test_velocity_cli():
    """Verify click CLI for velocity analytics."""
    runner = CliRunner()
    result = runner.invoke(main, ["--zone", "suwalki_corridor", "--months", "3"])
    assert result.exit_code == 0
    assert "CONSTRUCTION VELOCITY METRICS" in result.output
    assert "suwalki_corridor" in result.output
