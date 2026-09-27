"""Integration tests for Phase 3: ML Inference, Vectorization, and PostGIS Ingestion."""

import numpy as np

from scripts.generate_mock_data import create_synthetic_scene_pair
from src.inference.prithvi_detector import PrithviChangeDetector
from src.inference.vectorizer import PostGISPersistence, VectorizationEngine


def test_prithvi_detector_inference():
    detector = PrithviChangeDetector()
    t0, t1, _ = create_synthetic_scene_pair(height=64, width=64)

    # Scale to [0.0, 1.0] float32
    t0_float = t0.astype(np.float32) / 10000.0
    t1_float = t1.astype(np.float32) / 10000.0
    temporal_stack = np.stack([t0_float, t1_float], axis=0)  # Shape: (2, 6, 64, 64)

    binary_mask, prob_map = detector.detect_changes(temporal_stack, threshold=0.55)

    assert binary_mask.shape == (64, 64)
    assert prob_map.shape == (64, 64)
    # The synthetic data introduces a runway and radar facility; anomalies must be detected
    assert np.sum(binary_mask) > 0


def test_end_to_end_mock_inference_and_persistence():
    detector = PrithviChangeDetector()
    db_persistence = PostGISPersistence(dry_run=True)
    engine = VectorizationEngine(db_handler=db_persistence, min_cluster_pixels=10)

    t0, t1, _ = create_synthetic_scene_pair(height=64, width=64)
    t0_float = t0.astype(np.float32) / 10000.0
    t1_float = t1.astype(np.float32) / 10000.0
    temporal_stack = np.stack([t0_float, t1_float], axis=0)

    # 1. Run Prithvi change detection
    binary_mask, prob_map = detector.detect_changes(temporal_stack, threshold=0.55)

    # 2. Polygonize, classify via YOLO, and commit to PostGIS
    initial_count = len(db_persistence.committed_records)
    records = engine.process_and_persist(
        binary_mask=binary_mask,
        prob_map=prob_map,
        full_raster_cube=t1_float,
        bbox=[23.10, 54.05, 23.35, 54.25],
        baseline_timestamp="2026-05-15T08:30:00Z",
        detection_timestamp="2026-09-27T10:00:31Z",
        sensor_source="Sentinel-2A-MSI-L2A",
        stac_metadata={"item_id": "S2A_INTEGRATION_TEST", "cloud_cover": 1.2},
    )

    # 3. Assert pipeline completion and database record increment
    assert len(records) > 0
    assert len(db_persistence.committed_records) == initial_count + len(records)

    first_rec = records[0]
    assert first_rec.geometry["type"] == "Polygon"
    assert first_rec.classification in [
        "LOGISTICS_DEPOT",
        "RUNWAY_TAXIWAY",
        "RADAR_DOME",
        "DEFENSE_REVETMENT",
        "INDUSTRIAL_BUILDING",
        "UNKNOWN_STRUCTURE",
    ]
    assert 0.0 <= first_rec.confidence <= 1.0
    assert first_rec.baseline_timestamp == "2026-05-15T08:30:00Z"
    assert first_rec.detection_timestamp == "2026-09-27T10:00:31Z"
