"""Unit and Integration Tests for Local Observability & Dead Letter Queue (DLQ).

Tests:
- Dead Letter Queue dispatching and error capture
- Prometheus metrics generation and system gauge updates
- FastAPI /metrics scrape endpoint
- DLQ failure audit endpoint with RBAC enforcement
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.api.auth import create_access_token
from src.api.main import app
from src.ops.dlq import DeadLetterQueue, dlq_manager
from src.ops.metrics import (
    generate_metrics_payload,
    update_system_gauges,
)

client = TestClient(app)


def get_auth_header(role: str = "analyst", username: str = "analyst_viper"):
    token = create_access_token(
        data={"sub": username, "role": role, "id": "00000000-0000-0000-0000-000000000002"}
    )
    return {"Authorization": f"Bearer {token}"}


def test_dlq_capture_and_dispatch():
    dlq = DeadLetterQueue(dry_run=True)
    dlq.clear()

    # Simulate an exception (e.g. corrupted tile or rasterio alignment failure)
    try:
        raise ValueError("Corrupted Sentinel-2 L2A tile raster: missing B04 band")
    except Exception as exc:
        record = dlq.send_to_dlq(
            failed_topic="geoint-stac-ingest",
            original_payload={"item_id": "S2A_CORRUPT_001", "bbox": [23.1, 54.1, 23.2, 54.2]},
            error=exc,
            context={"tile_id": "T34UFB", "sensor": "Sentinel-2A"},
        )

    assert record["error_type"] == "ValueError"
    assert "Corrupted Sentinel-2" in record["error_message"]
    assert "Traceback" in record["stack_trace"]
    assert record["context"]["tile_id"] == "T34UFB"
    assert record["original_payload"]["item_id"] == "S2A_CORRUPT_001"

    # Verify retrieval
    messages = dlq.get_dlq_messages()
    assert len(messages) == 1
    assert messages[0]["dlq_id"] == record["dlq_id"]


def test_dlq_with_mock_kafka_producer(monkeypatch):
    mock_producer = MagicMock()
    mock_future = MagicMock()
    mock_producer.send.return_value = mock_future

    dlq = DeadLetterQueue(dry_run=False)
    monkeypatch.setattr(dlq, "_producer", mock_producer)

    try:
        raise RuntimeError("Prithvi foundation model Out of Memory (OOM)")
    except Exception as exc:
        record = dlq.send_to_dlq(
            failed_topic="geoint-inference-tasks",
            original_payload={"item_id": "S2A_OOM_002"},
            error=exc,
        )

    mock_producer.send.assert_called_once()
    mock_future.get.assert_called_once()
    assert record["error_type"] == "RuntimeError"


def test_prometheus_metrics_generation():
    update_system_gauges(
        disk_remaining_bytes={"caelum-chips": 85000000000},
        gpu_utilization=42.5,
        kafka_lag=15,
    )
    payload, media_type = generate_metrics_payload()
    assert isinstance(payload, bytes)
    text = payload.decode("utf-8")
    assert "caelum_kafka_queue_lag" in text
    assert "caelum_gpu_memory_utilization_percent" in text
    assert "caelum_minio_disk_space_remaining_bytes" in text


def test_fastapi_prometheus_endpoint():
    # Make a few requests to populate metrics
    client.get("/api/v1/health")

    # Scrape /metrics
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.content.decode("utf-8")
    assert "caelum_http_requests_total" in text
    assert "caelum_http_request_duration_seconds" in text


def test_ops_dlq_endpoint_rbac():
    # Trigger a DLQ event in global manager
    try:
        raise KeyError("Missing essential STAC asset href")
    except Exception as exc:
        dlq_manager.send_to_dlq(
            failed_topic="geoint-stac-ingest",
            original_payload={"item_id": "S2A_MISSING_ASSET"},
            error=exc,
        )

    # Viewer should be forbidden
    viewer_headers = get_auth_header(role="viewer", username="viewer_01")
    res = client.get("/api/v1/ops/dlq", headers=viewer_headers)
    assert res.status_code == 403

    # Analyst should succeed
    analyst_headers = get_auth_header(role="analyst", username="analyst_viper")
    res_analyst = client.get("/api/v1/ops/dlq", headers=analyst_headers)
    assert res_analyst.status_code == 200
    events = res_analyst.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    assert any(e["error_type"] == "KeyError" for e in events)
