"""Unit tests for Milestone 4: Admin UI & Dynamic Configuration Bindings.

Validates:
- STAC poller dynamic geofence fetching from PostGIS system_configurations
- Fallback behavior on database error / empty configs
- Dynamic polling interval retrieval
- Vectorizer confidence threshold filtering bound to database state
"""

import json
from unittest.mock import MagicMock, patch

import numpy as np

from src.inference.vectorizer import PostGISPersistence, VectorizationEngine
from src.ingestion.stac_poller import DEFAULT_EASTERN_EUROPE_BBOX, STACIngestionWorker


def test_stac_poller_fetch_dynamic_geofences_success():
    """Verify that STAC poller successfully retrieves configured geofences from DB."""
    worker = STACIngestionWorker(dry_run=True)

    mock_geofences_json = json.dumps(
        [
            {"name": "Suwalki Corridor", "bbox": [23.00, 54.00, 23.50, 54.40]},
            {"name": "Gotland Basin", "bbox": [18.00, 57.00, 19.50, 58.00]},
        ]
    )

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (mock_geofences_json,)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("psycopg2.connect", return_value=mock_conn):
        geofences = worker.fetch_target_geofences_from_db()

    assert len(geofences) == 2
    assert geofences[0]["name"] == "Suwalki Corridor"
    assert geofences[0]["bbox"] == [23.00, 54.00, 23.50, 54.40]
    assert geofences[1]["name"] == "Gotland Basin"


def test_stac_poller_fetch_dynamic_geofences_fallback():
    """Verify fallback to default Eastern Europe bbox when DB fails."""
    worker = STACIngestionWorker(dry_run=True)

    with patch("psycopg2.connect", side_effect=Exception("Database connection timeout")):
        geofences = worker.fetch_target_geofences_from_db()

    assert len(geofences) == 1
    assert geofences[0]["bbox"] == DEFAULT_EASTERN_EUROPE_BBOX


def test_stac_poller_fetch_polling_interval():
    """Verify dynamic polling interval fetching."""
    worker = STACIngestionWorker(dry_run=True)

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = ("900",)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("psycopg2.connect", return_value=mock_conn):
        interval = worker.fetch_polling_interval_from_db(default_interval=300)
    assert interval == 900

    # Fallback case
    with patch("psycopg2.connect", side_effect=Exception("DB down")):
        fallback_interval = worker.fetch_polling_interval_from_db(default_interval=300)
    assert fallback_interval == 300


def test_stac_poller_run_polling_cycle_dynamic():
    """Verify multi-geofence polling execution."""
    worker = STACIngestionWorker(dry_run=True)

    with patch.object(
        worker,
        "fetch_target_geofences_from_db",
        return_value=[
            {"name": "Zone A", "bbox": [23.0, 54.0, 23.2, 54.2]},
            {"name": "Zone B", "bbox": [23.3, 54.3, 23.5, 54.5]},
        ],
    ):
        with patch.object(worker, "query_sentinel2_l2a", return_value=[]):
            published = worker.run_polling_cycle(bbox=None, days_lookback=3)
            assert published == 0


def test_postgis_get_system_config():
    """Verify PostGISPersistence.get_system_config helper."""
    persistence = PostGISPersistence(dry_run=False)

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = ("0.85",)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    persistence._conn = mock_conn

    val = persistence.get_system_config("ml_confidence_threshold")
    assert val == "0.85"

    # Exception case
    mock_cur.execute.side_effect = Exception("SQL syntax error")
    fallback = persistence.get_system_config("ml_confidence_threshold", default="0.60")
    assert fallback == "0.60"


def test_vectorizer_dynamic_confidence_threshold_filtering():
    """Verify that detections below dynamic ml_confidence_threshold are filtered out."""
    db_mock = MagicMock()
    # Configure high threshold: 0.85
    db_mock.get_system_config.return_value = "0.85"

    engine = VectorizationEngine(db_handler=db_mock, min_cluster_pixels=4)

    # Mock polygon extraction: 2 clusters
    mock_polygons = [
        ({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}, (0, 0, 5, 5), 25),
        (
            {"type": "Polygon", "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 2]]]},
            (5, 5, 10, 10),
            25,
        ),
    ]

    # Cluster 1: confidence 0.92 (exceeds 0.85 -> accepted)
    # Cluster 2: confidence 0.70 (below 0.85 -> rejected)
    high_conf_cls = MagicMock(label="RADAR_DOME", confidence=0.92)
    low_conf_cls = MagicMock(label="UNKNOWN_STRUCTURE", confidence=0.70)

    engine.polygonize_binary_mask = MagicMock(return_value=mock_polygons)
    engine.classifier.classify_cluster = MagicMock(side_effect=[high_conf_cls, low_conf_cls])

    dummy_mask = np.ones((16, 16), dtype=np.uint8)
    dummy_prob = np.ones((16, 16), dtype=np.float32) * 0.8
    dummy_cube = np.random.uniform(0, 1, size=(6, 16, 16)).astype(np.float32)

    records = engine.process_and_persist(
        binary_mask=dummy_mask,
        prob_map=dummy_prob,
        full_raster_cube=dummy_cube,
        bbox=[23.0, 54.0, 23.5, 54.5],
        baseline_timestamp="2026-05-15T08:30:00Z",
        detection_timestamp="2026-06-01T10:00:00Z",
    )

    # Only the detection with confidence >= 0.85 was committed
    assert len(records) == 1
    assert records[0].classification == "RADAR_DOME"
    assert records[0].confidence == 0.92
    assert db_mock.insert_detection.call_count == 1
