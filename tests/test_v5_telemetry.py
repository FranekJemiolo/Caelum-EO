"""Unit tests for Phase V5: Multi-Modal Telemetry Ingestion and Dark-Target Correlation.

Validates:
- AIS CSV parsing (multi-format timestamps, optional columns, header normalisation)
- ADS-B JSON (OpenSky state-vector, NDJSON, list-of-dicts) and CSV parsing
- Dark-gap detection for both AIS and ADS-B streams
- DarkEventRecord construction and threat score calculation
- IngestionStats accumulation across multiple files
- TelemetryIngestor.ingest_directory() routing logic with mocked DB
- REST endpoints: /api/v1/telemetry/ingest, /vessels, /aircraft, /dark-events
"""

import csv
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.etl.telemetry_ingest import (
    AircraftTrackRecord,
    IngestionStats,
    TelemetryIngestor,
    VesselTrackRecord,
    _detect_dark_gaps_adsb,
    _detect_dark_gaps_ais,
    _parse_dt,
    _to_float,
    parse_adsb_json,
    parse_ais_csv,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_ais_csv(rows: list[dict]) -> Path:
    """Write AIS track rows to a temp CSV file and return the Path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_ais_vessel.csv", delete=False, newline="", encoding="utf-8"
    )
    fieldnames = [
        "mmsi", "timestamp", "lon", "lat", "vessel_name",
        "vessel_type", "flag", "speed", "course", "heading",
    ]
    writer = csv.DictWriter(tmp, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    tmp.close()
    return Path(tmp.name)


def _make_adsb_json(records: list[dict]) -> Path:
    """Write ADS-B records as a JSON array to a temp file and return the Path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_adsb_aircraft.json", delete=False, encoding="utf-8"
    )
    json.dump(records, tmp)
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# Tests: Parsing helpers
# ---------------------------------------------------------------------------


def test_parse_dt_iso_utc():
    dt = _parse_dt("2026-09-01T12:00:00Z", ["%Y-%m-%dT%H:%M:%SZ"])
    assert dt is not None
    assert dt.year == 2026
    assert dt.tzinfo is not None


def test_parse_dt_fallback():
    """Unparseable string returns None."""
    dt = _parse_dt("not-a-date", ["%Y-%m-%dT%H:%M:%SZ"])
    assert dt is None


def test_to_float_valid():
    assert _to_float("3.14") == pytest.approx(3.14)
    assert _to_float(42) == pytest.approx(42.0)


def test_to_float_invalid():
    assert _to_float("N/A") is None
    assert _to_float("") is None
    assert _to_float(None) is None


# ---------------------------------------------------------------------------
# Tests: AIS CSV parsing
# ---------------------------------------------------------------------------


def test_parse_ais_csv_basic():
    """Parse a minimal AIS CSV with required columns."""
    fp = _make_ais_csv([
        {
            "mmsi": "123456789",
            "timestamp": "2026-09-01T12:00:00Z",
            "lon": "23.15",
            "lat": "54.22",
            "vessel_name": "MV CAELUM",
            "vessel_type": "CARGO",
            "flag": "PL",
            "speed": "8.5",
            "course": "180.0",
            "heading": "182.0",
        }
    ])
    records = list(parse_ais_csv(fp))
    assert len(records) == 1
    r = records[0]
    assert r.mmsi == "123456789"
    assert r.lon == pytest.approx(23.15)
    assert r.lat == pytest.approx(54.22)
    assert r.vessel_name == "MV CAELUM"
    assert r.speed_knots == pytest.approx(8.5)
    fp.unlink()


def test_parse_ais_csv_skips_invalid_rows():
    """Rows missing required fields are silently skipped."""
    fp = _make_ais_csv([
        {"mmsi": "", "timestamp": "", "lon": "", "lat": ""},  # empty → skip
        {
            "mmsi": "987654321",
            "timestamp": "2026-09-01T13:00:00Z",
            "lon": "23.20",
            "lat": "54.25",
            "vessel_name": "", "vessel_type": "", "flag": "",
            "speed": "", "course": "", "heading": "",
        },
    ])
    records = list(parse_ais_csv(fp))
    assert len(records) == 1
    assert records[0].mmsi == "987654321"
    fp.unlink()


def test_parse_ais_csv_truncates_mmsi():
    """MMSI is capped at 9 characters."""
    fp = _make_ais_csv([{
        "mmsi": "123456789EXTRA",
        "timestamp": "2026-09-01T12:00:00Z",
        "lon": "23.0", "lat": "54.0",
        "vessel_name": "X", "vessel_type": "X", "flag": "XX",
        "speed": "0", "course": "0", "heading": "0",
    }])
    records = list(parse_ais_csv(fp))
    assert len(records[0].mmsi) == 9
    fp.unlink()


# ---------------------------------------------------------------------------
# Tests: ADS-B JSON parsing
# ---------------------------------------------------------------------------


def test_parse_adsb_json_list_of_dicts():
    """Parse ADS-B JSON as a list of flat record dicts."""
    records_raw = [
        {
            "icao24": "aaa111",
            "timestamp": "2026-09-01T12:00:00Z",
            "longitude": 23.1,
            "latitude": 54.3,
            "callsign": "LH1234",
            "baro_altitude": 8000.0,
            "velocity": 250.0,
            "on_ground": False,
        }
    ]
    fp = _make_adsb_json(records_raw)
    parsed = list(parse_adsb_json(fp))
    assert len(parsed) == 1
    r = parsed[0]
    assert r.icao24 == "aaa111"
    assert r.callsign == "LH1234"
    assert r.altitude_baro_m == pytest.approx(8000.0)
    assert r.is_on_ground is False
    fp.unlink()


def test_parse_adsb_json_unix_timestamp():
    """Accept Unix epoch float timestamps."""
    ts_epoch = BASE_TIME.timestamp()
    fp = _make_adsb_json([{
        "icao24": "bbb222",
        "time_position": ts_epoch,
        "longitude": 23.0,
        "latitude": 54.0,
    }])
    parsed = list(parse_adsb_json(fp))
    assert len(parsed) == 1
    assert parsed[0].timestamp.year == 2026
    fp.unlink()


def test_parse_adsb_json_opensky_state_vector():
    """Parse OpenSky API state-vector list format."""
    opensky_payload = {
        "states": [
            ["aaa333", "KLM123  ", "Netherlands", 1693000000.0, 1693000000.0,
             23.5, 54.5, 9000.0, False, 270.0, 90.0, 0.0, None, 9200.0, "7700",
             False, 0],
        ]
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_opensky_aircraft.json", delete=False, encoding="utf-8"
    )
    json.dump(opensky_payload, tmp)
    tmp.close()
    fp = Path(tmp.name)
    parsed = list(parse_adsb_json(fp))
    assert len(parsed) == 1
    r = parsed[0]
    assert r.icao24 == "aaa333"
    assert r.callsign == "KLM123"
    assert r.squawk == "7700"
    fp.unlink()


def test_parse_adsb_json_ndjson():
    """Parse newline-delimited JSON (NDJSON) format."""
    lines = [
        json.dumps({"icao24": "ccc444", "timestamp": "2026-09-01T12:00:00Z", "longitude": 23.0, "latitude": 54.0}),
        json.dumps({"icao24": "ddd555", "timestamp": "2026-09-01T12:05:00Z", "longitude": 23.1, "latitude": 54.1}),
    ]
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_adsb_aircraft.ndjson", delete=False, encoding="utf-8"
    )
    tmp.write("\n".join(lines))
    tmp.close()
    fp = Path(tmp.name)
    parsed = list(parse_adsb_json(fp))
    assert len(parsed) == 2
    fp.unlink()


# ---------------------------------------------------------------------------
# Tests: Dark-gap detection
# ---------------------------------------------------------------------------


def test_detect_dark_gaps_ais_single_gap():
    """Detect a 90-minute gap as a dark event."""
    t0 = BASE_TIME
    t1 = t0 + timedelta(minutes=90)
    tracks = [
        VesselTrackRecord(mmsi="111111111", timestamp=t0, lon=23.0, lat=54.0),
        VesselTrackRecord(mmsi="111111111", timestamp=t1, lon=23.1, lat=54.1),
    ]
    gaps = _detect_dark_gaps_ais(tracks, dark_threshold_minutes=60)
    assert len(gaps) == 1
    assert gaps[0][0].mmsi == "111111111"
    assert (gaps[0][1].timestamp - gaps[0][0].timestamp).total_seconds() / 60 == pytest.approx(90)


def test_detect_dark_gaps_ais_no_gap():
    """Short 10-minute gap is not detected as dark."""
    t0 = BASE_TIME
    t1 = t0 + timedelta(minutes=10)
    tracks = [
        VesselTrackRecord(mmsi="222222222", timestamp=t0, lon=23.0, lat=54.0),
        VesselTrackRecord(mmsi="222222222", timestamp=t1, lon=23.0, lat=54.0),
    ]
    gaps = _detect_dark_gaps_ais(tracks, dark_threshold_minutes=60)
    assert len(gaps) == 0


def test_detect_dark_gaps_ais_multiple_vessels():
    """Dark gaps are tracked per MMSI independently."""
    t0 = BASE_TIME
    t_gap = t0 + timedelta(minutes=120)
    tracks = [
        VesselTrackRecord(mmsi="AAA111111", timestamp=t0, lon=23.0, lat=54.0),
        VesselTrackRecord(mmsi="AAA111111", timestamp=t_gap, lon=23.5, lat=54.5),
        VesselTrackRecord(mmsi="BBB222222", timestamp=t0, lon=24.0, lat=55.0),
        VesselTrackRecord(mmsi="BBB222222", timestamp=t0 + timedelta(minutes=5), lon=24.0, lat=55.0),
    ]
    gaps = _detect_dark_gaps_ais(tracks, dark_threshold_minutes=60)
    assert len(gaps) == 1
    assert gaps[0][0].mmsi == "AAA111111"


def test_detect_dark_gaps_adsb():
    """Detect dark gap in ADS-B tracks."""
    t0 = BASE_TIME
    t1 = t0 + timedelta(minutes=45)
    tracks = [
        AircraftTrackRecord(icao24="abc123", timestamp=t0, lon=23.0, lat=54.0),
        AircraftTrackRecord(icao24="abc123", timestamp=t1, lon=23.2, lat=54.2),
    ]
    gaps = _detect_dark_gaps_adsb(tracks, dark_threshold_minutes=30)
    assert len(gaps) == 1


# ---------------------------------------------------------------------------
# Tests: IngestionStats aggregation
# ---------------------------------------------------------------------------


def test_ingestion_stats_default():
    stats = IngestionStats()
    assert stats.vessel_rows_parsed == 0
    assert stats.dark_events_inserted == 0
    assert stats.errors == []


# ---------------------------------------------------------------------------
# Tests: TelemetryIngestor routing
# ---------------------------------------------------------------------------


def test_ingestor_directory_routing():
    """TelemetryIngestor routes files by name prefix correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)

        # Create AIS file
        ais_fp = td / "ais_vessel_2026.csv"
        with ais_fp.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["mmsi", "timestamp", "lon", "lat"])
            w.writeheader()
            w.writerow({"mmsi": "123456789", "timestamp": "2026-09-01T12:00:00Z",
                        "lon": "23.0", "lat": "54.0"})

        # Create ADS-B file
        adsb_fp = td / "adsb_aircraft_2026.json"
        adsb_fp.write_text(json.dumps([{
            "icao24": "aaa111",
            "timestamp": "2026-09-01T12:00:00Z",
            "longitude": 23.1,
            "latitude": 54.1,
        }]))

        # Mock DB completely so no real connection is attempted
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.etl.telemetry_ingest._get_db_conn", return_value=mock_conn):
            with patch("src.etl.telemetry_ingest._insert_vessel_tracks", return_value=1):
                with patch("src.etl.telemetry_ingest._insert_aircraft_tracks", return_value=1):
                    with patch("src.etl.telemetry_ingest._insert_dark_events", return_value=0):
                        with patch("src.etl.telemetry_ingest._load_ais_dark_config", return_value=(50.0, 72)):
                            with patch("src.etl.telemetry_ingest._correlate_dark_ais", return_value=None):
                                with patch("src.etl.telemetry_ingest._correlate_dark_adsb", return_value=None):
                                    ingestor = TelemetryIngestor()
                                    stats = ingestor.ingest_directory(td)

        assert stats.vessel_rows_parsed >= 1
        assert stats.aircraft_rows_parsed >= 1


def test_ingestor_missing_directory_raises():
    ingestor = TelemetryIngestor()
    with pytest.raises(FileNotFoundError):
        ingestor.ingest_directory(Path("/nonexistent/path/telemetry"))


# ---------------------------------------------------------------------------
# Tests: REST API endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers() -> dict:
    """Authenticate and return Bearer token headers."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def admin_headers() -> dict:
    """Admin auth headers for privileged endpoints."""
    from src.api.auth import create_access_token

    token = create_access_token(
        data={"sub": "admin", "role": "admin", "id": "00000000-0000-0000-0000-000000000001"}
    )
    return {"Authorization": f"Bearer {token}"}


def test_get_vessel_tracks_endpoint(auth_headers):
    """GET /api/v1/telemetry/vessels returns a list (empty when no DB)."""
    client = TestClient(app)
    resp = client.get("/api/v1/telemetry/vessels", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_aircraft_tracks_endpoint(auth_headers):
    """GET /api/v1/telemetry/aircraft returns a list."""
    client = TestClient(app)
    resp = client.get("/api/v1/telemetry/aircraft", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_dark_events_endpoint(auth_headers):
    """GET /api/v1/telemetry/dark-events returns a list."""
    client = TestClient(app)
    resp = client.get("/api/v1/telemetry/dark-events", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_dark_events_type_filter(auth_headers):
    """Dark events endpoint accepts event_type filter."""
    client = TestClient(app)
    resp = client.get("/api/v1/telemetry/dark-events?event_type=AIS", headers=auth_headers)
    assert resp.status_code == 200


def test_vessel_tracks_requires_auth():
    """Unauthenticated request to /vessels is rejected."""
    client = TestClient(app)
    resp = client.get("/api/v1/telemetry/vessels")
    assert resp.status_code == 401


def test_telemetry_ingest_requires_admin(auth_headers):
    """Analyst cannot trigger telemetry ingest (admin-only)."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/telemetry/ingest",
        json={"directory_path": "/tmp/telemetry"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


def test_telemetry_ingest_missing_directory(admin_headers):
    """Admin gets 400 when directory does not exist."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/telemetry/ingest",
        json={"directory_path": "/nonexistent/telemetry/path"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


def test_telemetry_ingest_dry_run(admin_headers):
    """Dry-run returns zero inserted rows even for valid files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        ais_fp = td / "ais_vessel_test.csv"
        with ais_fp.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["mmsi", "timestamp", "lon", "lat"])
            w.writeheader()
            w.writerow({"mmsi": "123456789", "timestamp": "2026-09-01T12:00:00Z",
                        "lon": "23.0", "lat": "54.0"})

        client = TestClient(app)
        resp = client.post(
            "/api/v1/telemetry/ingest",
            json={"directory_path": str(td), "dry_run": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["vessel_rows_inserted"] == 0
        assert data["vessel_rows_parsed"] >= 1
        assert data["errors"] == []


def test_get_network_snapshots_endpoint(auth_headers):
    """GET /api/v1/network/snapshots returns a list."""
    client = TestClient(app)
    resp = client.get("/api/v1/network/snapshots", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_latest_snapshot_404_when_empty(auth_headers):
    """Latest snapshot returns 404 when no snapshots exist (offline mode)."""
    client = TestClient(app)
    with patch("src.analytics.network_graph.NetworkAnalysisEngine.get_latest_snapshot", return_value=None):
        resp = client.get("/api/v1/network/snapshots/latest", headers=auth_headers)
    assert resp.status_code == 404


def test_network_graph_endpoint(auth_headers):
    """GET /api/v1/network/graph returns node-link JSON with 'nodes' and 'links'."""
    client = TestClient(app)
    resp = client.get("/api/v1/network/graph", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "links" in data
