"""Integration tests for Phase 3: ML Inference, Vectorization, and PostGIS Ingestion."""

import numpy as np
import pytest

torch = pytest.importorskip(
    "torch", reason="torch not installed; install the 'ml' extra to run ML tests"
)  # noqa: E501

from scripts.generate_mock_data import create_synthetic_scene_pair  # noqa: E402
from src.inference.prithvi_detector import PrithviChangeDetector  # noqa: E402
from src.inference.vectorizer import PostGISPersistence, VectorizationEngine  # noqa: E402


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


def test_inference_coordinator_stac_event():
    from src.inference.detector import PRITHVI_BAND_NAMES, InferenceCoordinator

    db_persistence = PostGISPersistence(dry_run=True)
    engine = VectorizationEngine(db_handler=db_persistence, min_cluster_pixels=5)
    coordinator = InferenceCoordinator(device="cpu", vectorizer=engine)

    dummy_event = {
        "item_id": "S2A_MSIL2A_TEST_EVENT",
        "bbox": [23.10, 54.05, 23.35, 54.25],
        "datetime": "2026-09-27T12:00:00Z",
        "cloud_cover": 2.0,
        "bands": {b: {"band_name": b, "href": f"https://mock/{b}.tif"} for b in PRITHVI_BAND_NAMES},
    }

    mask, prob, records = coordinator.process_stac_event(dummy_event)
    assert mask.shape == (256, 256)
    assert prob.shape == (256, 256)
    assert len(records) > 0
    assert records[0].stac_metadata["item_id"] == "S2A_MSIL2A_TEST_EVENT"


def test_yolo_classifier_direct():
    from src.inference.yolo_classifier import VALID_CLASSES, YOLOInfrastructureClassifier

    classifier = YOLOInfrastructureClassifier()
    chip = np.random.uniform(0.1, 0.9, size=(6, 32, 32)).astype(np.float32)

    # Test radar-like anomaly
    res_radar = classifier.classify_cluster(
        chip=chip, bbox=(10, 10, 20, 20), pixel_count=45, mean_anomaly_prob=0.88
    )
    assert res_radar.label in VALID_CLASSES
    assert 0.0 <= res_radar.confidence <= 1.0

    # Test elongated runway-like anomaly
    res_runway = classifier.classify_cluster(
        chip=chip, bbox=(10, 10, 15, 60), pixel_count=200, mean_anomaly_prob=0.92
    )
    assert res_runway.label in VALID_CLASSES
