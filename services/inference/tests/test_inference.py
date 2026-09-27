"""Unit tests for ML Inference Components (Prithvi, YOLO-OBB, GeoSAM)."""

import numpy as np
import pytest

from services.inference.cluster_extractor import AnomalyCluster, SpatialClusterExtractor
from services.inference.config import ModelSettings
from services.inference.geosam_vectorizer import GeoSAMVectorizer
from services.inference.pipeline import GEOINTInferencePipeline
from services.inference.prithvi_detector import PrithviChangeDetector
from services.inference.yolo_classifier import YOLOInfrastructureClassifier


@pytest.fixture
def synthetic_temporal_pair():
    """Create a synthetic (2, 6, 64, 64) temporal image pair.

    T0: Flat background (0.1).
    T1: Flat background (0.1) with an artificial 16x16 structural anomaly (0.9) in center.
    """
    t0 = np.ones((6, 64, 64), dtype=np.float32) * 0.1
    t1 = np.ones((6, 64, 64), dtype=np.float32) * 0.1
    # Introduce structural change in center
    t1[:, 24:40, 24:40] = 0.9
    return np.stack([t0, t1], axis=0)


def test_prithvi_detector_inference(synthetic_temporal_pair):
    detector = PrithviChangeDetector()
    binary_mask, prob_map = detector.detect_changes(synthetic_temporal_pair, threshold=0.5)

    assert binary_mask.shape == (64, 64)
    assert prob_map.shape == (64, 64)
    assert binary_mask.dtype == np.uint8
    # Center anomaly should register higher change probability than background
    assert prob_map[32, 32] > prob_map[5, 5]


def test_spatial_cluster_extraction():
    extractor = SpatialClusterExtractor(ModelSettings(min_cluster_pixels=10))

    # Mask with a 10x10 block of 1s
    binary_mask = np.zeros((64, 64), dtype=np.uint8)
    binary_mask[20:30, 20:30] = 1
    prob_map = np.ones((64, 64), dtype=np.float32) * 0.85
    geo_bounds = [20.0, 50.0, 21.0, 51.0]

    clusters = extractor.extract_clusters(binary_mask, prob_map, geo_bounds)

    assert len(clusters) == 1
    c = clusters[0]
    assert c.pixel_count == 100
    assert c.mean_confidence == pytest.approx(0.85)
    assert len(c.geo_bbox) == 4
    # Centroid must be inside the bounding box
    assert c.geo_bbox[0] <= c.geo_centroid[0] <= c.geo_bbox[2]
    assert c.geo_bbox[1] <= c.geo_centroid[1] <= c.geo_bbox[3]


def test_yolo_classifier():
    classifier = YOLOInfrastructureClassifier()
    cluster = AnomalyCluster(
        cluster_id=1,
        pixel_bbox=(20, 20, 25, 25),
        pixel_centroid=(22.5, 22.5),
        geo_bbox=[20.2, 50.2, 20.3, 50.3],
        geo_centroid=[20.25, 50.25],
        pixel_count=36,
        mean_confidence=0.9,
    )
    chip = np.ones((6, 32, 32), dtype=np.float32)

    result = classifier.classify_chip(chip, cluster)
    assert result.classification in classifier.target_classes
    assert 0.0 <= result.confidence <= 1.0
    assert result.cluster_id == 1


def test_geosam_vectorizer():
    vectorizer = GeoSAMVectorizer()
    cluster = AnomalyCluster(
        cluster_id=1,
        pixel_bbox=(20, 20, 30, 30),
        pixel_centroid=(25.0, 25.0),
        geo_bbox=[20.2, 50.2, 20.3, 50.3],
        geo_centroid=[20.25, 50.25],
        pixel_count=100,
        mean_confidence=0.92,
    )
    chip = np.ones((6, 32, 32), dtype=np.float32)

    polygon = vectorizer.segment_and_vectorize(
        image_chip=chip,
        cluster=cluster,
        offset_row_col=(10, 10),
        geo_bounds=[20.0, 50.0, 21.0, 51.0],
        full_raster_shape=(64, 64),
    )

    assert polygon["type"] == "Polygon"
    coords = polygon["coordinates"][0]
    assert len(coords) >= 4
    # Must be a closed polygon ring
    assert coords[0] == coords[-1]


def test_end_to_end_inference_pipeline(synthetic_temporal_pair):
    pipeline = GEOINTInferencePipeline()
    geo_bounds = [22.8, 53.8, 24.5, 54.7]

    records = pipeline.process_scene_pair(
        temporal_stack=synthetic_temporal_pair,
        geo_bounds=geo_bounds,
        detection_date="2026-09-27T12:00:00Z",
        source_metadata={"scene_id": "TEST_SCENE_001"},
    )

    # Should find at least one detection corresponding to the center anomaly
    assert len(records) >= 1
    rec = records[0]
    assert rec.geometry["type"] == "Polygon"
    assert rec.classification in pipeline.yolo.target_classes
    assert rec.confidence > 0.5
    assert rec.detection_date == "2026-09-27T12:00:00Z"
    assert rec.source_imagery["scene_id"] == "TEST_SCENE_001"
