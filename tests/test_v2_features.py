"""Unit & Integration Tests for Project Caelum-EO Version Two Features.

Tests:
1. Sentinel-1 SAR ingestion, speckle filtering, and radiometric dB conversion.
2. Multi-modal 8-band tensor assembly (6 Optical + 2 SAR).
3. Cloud-adaptive cross-attention change detection neural head.
4. MGRS grid zone calculation and Citus PostGIS sharding manager.
5. Distributed MVT vector tile cache with tier-1 LRU and ETag headers.
6. Continuous active learning harvesting and LoRA adapter parameter-efficient tuning.
7. Tactical edge delta protocol compression (< 1.5 KB), HMAC signing, and sync manager.
8. Version Two FastAPI endpoints.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
Version Two Specification
"""

from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.auth import create_access_token
from src.api.main import app
from src.api.tile_cache import DistributedTileCache
from src.db.citus_sharding import CitusShardingManager, calculate_mgrs_tile_id
from src.edge.delta_protocol import DeltaProtocolEncoder
from src.edge.sync import EdgeSyncManager
from src.etl.cdse_client import STACBandMeta, STACItemPayload
from src.etl.sar_ingest import (
    MultiModalTensorAssembler,
    SARItemPayload,
    Sentinel1SARProcessor,
)
from src.mlops.active_learning import ActiveLearningHarvestEngine, LoRATrainingWorker


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict:
    token = create_access_token(
        data={"sub": "admin", "role": "admin"},
        expires_delta=timedelta(minutes=60),
    )
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# 1. Multi-Modal SAR Ingest & Tensor Assembly Tests
# --------------------------------------------------------------------------


def test_sentinel1_sar_processor_synthetic():
    processor = Sentinel1SARProcessor()
    vv = processor.read_windowed_sar_band(
        band_href=None, bbox=[23.0, 54.0, 23.5, 54.5], target_shape=(64, 64), polarization="VV"
    )
    vh = processor.read_windowed_sar_band(
        band_href=None, bbox=[23.0, 54.0, 23.5, 54.5], target_shape=(64, 64), polarization="VH"
    )
    assert vv.shape == (64, 64)
    assert vh.shape == (64, 64)
    assert 0.0 <= np.mean(vv) <= 1.0

    # Test speckle filtering
    speckled = np.random.uniform(0.1, 0.9, (32, 32)).astype(np.float32)
    filtered = processor._fast_speckle_filter(speckled)
    assert filtered.shape == (32, 32)

    lee_filtered = processor.apply_lee_speckle_filter(speckled, window_size=3)
    assert lee_filtered.shape == (32, 32)


def test_multimodal_tensor_assembly():
    assembler = MultiModalTensorAssembler()

    optical_payload = STACItemPayload(
        item_id="S2_TEST_ITEM_01",
        collection="sentinel-2-l2a",
        datetime="2026-09-27T10:00:00Z",
        bbox=[23.1, 54.1, 23.3, 54.3],
        cloud_cover=1.2,
        platform="Sentinel-2A",
        mgrs_tile="35UPB",
        bands={
            b: STACBandMeta(href="", band=b) for b in ["B02", "B03", "B04", "B8A", "B11", "B12"]
        },
    )
    sar_payload = SARItemPayload(
        item_id="S1_TEST_ITEM_01",
        acquisition_date="2026-09-27T10:00:00Z",
        bbox=[23.1, 54.1, 23.3, 54.3],
    )

    fused_cube, cloud_mask = assembler.assemble_multimodal_scene(
        optical_payload, sar_payload, target_shape=(64, 64)
    )
    assert fused_cube.shape == (8, 64, 64)
    assert cloud_mask.shape == (64, 64)

    t0_opt = optical_payload
    t1_opt = optical_payload
    stack, weights = assembler.create_multimodal_temporal_stack(
        t0_opt, t1_opt, target_shape=(64, 64)
    )
    assert stack.shape == (2, 8, 64, 64)
    assert weights.shape == (2, 64, 64)


# --------------------------------------------------------------------------
# 2. Multi-Modal Cross-Attention Change Detection Tests
# --------------------------------------------------------------------------


def test_multimodal_change_detector_forward():
    pytest.importorskip("torch", reason="torch not installed; install the 'ml' extra")
    from src.inference.multimodal_detector import MultiModalChangeDetector

    detector = MultiModalChangeDetector(threshold=0.55)
    temporal_stack = np.random.uniform(0.1, 0.8, (2, 8, 64, 64)).astype(np.float32)
    cloud_weights = np.zeros((2, 64, 64), dtype=np.float32)
    cloud_weights[:, 10:30, 10:30] = 1.0  # Simulate localized cloud obstruction

    binary_mask, prob_map = detector.detect_changes(
        temporal_stack=temporal_stack, cloud_weights=cloud_weights
    )

    assert binary_mask.shape == (64, 64)
    assert prob_map.shape == (64, 64)
    assert binary_mask.dtype == np.uint8
    assert np.all((prob_map >= 0.0) & (prob_map <= 1.0))


# --------------------------------------------------------------------------
# 3. Citus Sharding & MGRS Grid Zone Tests
# --------------------------------------------------------------------------


def test_calculate_mgrs_tile_id():
    # Suwalki Corridor coordinates (approx 23.23 Lon, 54.14 Lat)
    mgrs_tile = calculate_mgrs_tile_id(23.23, 54.14)
    assert isinstance(mgrs_tile, str)
    assert len(mgrs_tile) >= 4
    assert mgrs_tile.startswith("34") or mgrs_tile.startswith("35")

    # Migration DDL generation
    ddl = CitusShardingManager.get_v2_migration_ddl()
    assert len(ddl) >= 4
    assert any("mgrs_tile_id" in stmt for stmt in ddl)

    citus_sql = CitusShardingManager.get_citus_distribution_sql()
    assert "create_distributed_table" in citus_sql

    status = CitusShardingManager.check_sharding_status(None)
    assert "sharding_key" in status
    assert status["sharding_key"] == "mgrs_tile_id"


# --------------------------------------------------------------------------
# 4. Distributed Tile Cache Tests
# --------------------------------------------------------------------------


def test_distributed_tile_cache():
    cache = DistributedTileCache(max_in_memory_tiles=10)

    # Initial miss
    assert cache.get_tile("infrastructure_detections", 10, 500, 300) is None

    # Generate synthetic MVT and cache
    mvt_bytes = cache.generate_synthetic_mvt("infrastructure_detections", 10, 500, 300)
    assert len(mvt_bytes) > 0
    cache.set_tile("infrastructure_detections", 10, 500, 300, mvt_bytes)

    # Cache hit
    retrieved = cache.get_tile("infrastructure_detections", 10, 500, 300)
    assert retrieved == mvt_bytes

    # ETag verification
    etag = cache.compute_etag(mvt_bytes)
    assert etag.startswith('"') and etag.endswith('"')

    # Prewarming
    warmed = cache.prewarm_hotspots("infrastructure_detections", [(10, 1, 1), (10, 1, 2)])
    assert warmed == 2

    # Invalidation
    invalidated = cache.invalidate_layer("infrastructure_detections")
    assert invalidated >= 3

    stats = cache.get_stats()
    assert "hit_ratio_percent" in stats


# --------------------------------------------------------------------------
# 5. Continuous Active Learning & LoRA Pipeline Tests
# --------------------------------------------------------------------------


def test_active_learning_pipeline(tmp_path):
    harvest = ActiveLearningHarvestEngine(min_samples_to_trigger=2)
    audit_data = [
        {
            "detection_id": "d1",
            "review_status": "FALSE_POSITIVE",
            "previous_class": "RUNWAY_TAXIWAY",
            "confidence": 0.88,
            "reviewed_by": "analyst_viper",
        },
        {
            "detection_id": "d2",
            "review_status": "MISCLASSIFIED",
            "previous_class": "UNKNOWN_STRUCTURE",
            "new_class": "RADAR_DOME",
            "confidence": 0.92,
            "reviewed_by": "analyst_viper",
        },
        {
            "detection_id": "d3",
            "review_status": "VERIFIED",
            "previous_class": "DEFENSE_REVETMENT",
            "confidence": 0.95,
            "reviewed_by": "admin",
        },
    ]

    manifest = harvest.harvest_from_audit_records(audit_data)
    assert len(manifest) == 3
    assert manifest[0].sample_type == "HARD_NEGATIVE"
    assert manifest[1].sample_type == "CORRECTED_POSITIVE"
    assert manifest[2].sample_type == "VERIFIED_POSITIVE"

    worker = LoRATrainingWorker(output_weights_dir=str(tmp_path))
    initial_status = worker.get_status()
    assert initial_status.model_version == "Prithvi-EO-2.0-Base"

    updated_status = worker.train_lora_iteration(manifest, iteration_tag="v2.test")
    assert "LoRA-v2.test" in updated_status.model_version
    assert updated_status.hard_negatives_count == 1
    assert updated_status.positives_count == 2
    assert updated_status.fp_suppression_rate >= 0.70
    assert updated_status.staged_checkpoint is not None


# --------------------------------------------------------------------------
# 6. Tactical Edge Delta Protocol & Sync Manager Tests
# --------------------------------------------------------------------------


def test_tactical_edge_delta_protocol():
    encoder = DeltaProtocolEncoder(shared_secret="test_secret_key_123")

    coords = [
        (23.14800, 54.11800),
        (23.15600, 54.11800),
        (23.15600, 54.12600),
        (23.14800, 54.12600),
        (23.14800, 54.11800),
    ]

    payload = encoder.encode_delta(
        target_id="a1b2c3d4-e5f6-47a8-b901-23456789abcd",
        classification="RADAR_DOME",
        confidence=0.942,
        priority_score=92.0,
        coordinates=coords,
    )

    # Size must be compact (< 1.5 KB; here only ~60-80 bytes)
    assert len(payload) < 200

    delta = encoder.decode_delta(payload)
    assert delta.target_id == "a1b2c3d4-e5f6-47a8-b901-23456789abcd"
    assert delta.classification == "RADAR_DOME"
    assert abs(delta.confidence - 0.942) < 0.01
    assert delta.priority_score == 92.0
    assert len(delta.coordinates) == len(coords)
    assert delta.hmac_valid is True

    # Tampered signature detection
    tampered = payload[:-1] + (b"\x00" if payload[-1:] != b"\x00" else b"\x01")
    tampered_delta = encoder.decode_delta(tampered)
    assert tampered_delta.hmac_valid is False


def test_edge_sync_manager():
    sync = EdgeSyncManager(node_id="orin_unit_04")
    coords = [(23.15, 54.12), (23.16, 54.12), (23.16, 54.13), (23.15, 54.13)]

    sync.queue_detection_delta(
        target_id="b2c3d4e5-f6a7-48b9-c012-3456789abcde",
        classification="LOGISTICS_DEPOT",
        confidence=0.88,
        priority_score=78.0,
        coordinates=coords,
    )

    status = sync.get_status()
    assert status.pending_deltas_count == 1
    assert status.connected is True

    batch = sync.prepare_sync_batch()
    assert batch["batch_size"] == 1
    assert len(batch["deltas_b64"]) == 1

    # Receive batch at HQ
    applied = sync.receive_and_apply_batch(batch)
    assert len(applied) == 1
    assert applied[0].classification == "LOGISTICS_DEPOT"

    # Acknowledge
    sync.acknowledge_sync_batch(1)
    assert sync.get_status().pending_deltas_count == 0


# --------------------------------------------------------------------------
# 7. FastAPI Version Two Endpoints Integration Tests
# --------------------------------------------------------------------------


def test_api_v2_multimodal_status(test_client, auth_headers):
    res = test_client.get("/api/v1/multimodal/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert "bands" in data
    assert "SAR_VV" in data["bands"]
    assert "SAR_VH" in data["bands"]


def test_api_v2_vector_tile_caching(test_client):
    res = test_client.get("/api/v1/tiles/mvt/12/2315/1342")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/x-protobuf"
    assert "ETag" in res.headers
    assert "Cache-Control" in res.headers


def test_api_v2_mlops_and_active_learning(test_client, auth_headers):
    res_status = test_client.get("/api/v1/mlops/active-learning/status", headers=auth_headers)
    assert res_status.status_code == 200
    data = res_status.json()
    assert "model_version" in data
    assert "fp_suppression_rate" in data

    res_trigger = test_client.post(
        "/api/v1/mlops/active-learning/trigger?iteration_tag=v2.ci",
        headers=auth_headers,
    )
    assert res_trigger.status_code == 200
    res_data = res_trigger.json()
    assert "LoRA-v2.ci" in res_data["model_version"]


def test_api_v2_edge_sync_and_citus(test_client, auth_headers):
    res_edge = test_client.get("/api/v1/edge/sync/status", headers=auth_headers)
    assert res_edge.status_code == 200
    assert "node_id" in res_edge.json()

    res_citus = test_client.get("/api/v1/citus/status", headers=auth_headers)
    assert res_citus.status_code == 200
    assert res_citus.json()["sharding_key"] == "mgrs_tile_id"

    # Push batch
    sync = EdgeSyncManager()
    batch = sync.prepare_sync_batch()
    res_push = test_client.post("/api/v1/edge/sync/push", json=batch, headers=auth_headers)
    assert res_push.status_code == 200
    assert res_push.json()["status"] == "success"
