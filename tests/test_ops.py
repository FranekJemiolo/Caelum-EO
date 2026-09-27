"""Unit tests for Operational Reliability: High-Priority Webhook Alerting & Data Retention Pruning."""

import os
import time
from unittest.mock import MagicMock, patch

from src.api.webhooks import (
    build_geoint_alert_payload,
    dispatch_high_priority_alert,
)
from src.etl.pruner import prune_local_raw_rasters, run_pruning_cycle


def test_webhook_alert_payload_formatting():
    """Verify SIEM payload matches required defense intelligence structure."""
    detection = {
        "id": "det-12345-uuid",
        "classification": "RADAR_DOME",
        "confidence": 0.96,
        "priority_score": 0.92,
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "area_sq_meters": 1250.0,
        "sensor_source": "Sentinel-2A",
    }
    payload = build_geoint_alert_payload(detection)

    assert payload["event_type"] == "HIGH_PRIORITY_GEOINT_DETECTION"
    assert payload["severity"] == "CRITICAL"
    assert payload["priority_score"] == 0.92
    assert payload["classification"] == "RADAR_DOME"
    assert "RADAR_DOME" in payload["summary"]
    assert "ZONE-SUWALKI-CORRIDOR" in payload["summary"]


@patch("requests.post")
def test_webhook_dispatch_triggers_for_priority_over_threshold(mock_post):
    """Verify detections with priority_score > 0.85 dispatch alert payloads."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    detection = {
        "id": "det-high-priority",
        "classification": "DEFENSE_REVETMENT",
        "confidence": 0.94,
        "priority_score": 0.89,  # > 0.85 threshold
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
    }

    test_urls = ["https://siem.defense.internal/alerts", "https://hooks.slack.com/services/mock"]
    results = dispatch_high_priority_alert(detection, webhook_urls=test_urls)

    assert len(results) == 2
    assert all(r["status"] == "success" for r in results)
    assert mock_post.call_count == 2

    # Verify JSON payload passed to requests.post
    sent_payload = mock_post.call_args[1]["json"]
    assert sent_payload["detection_id"] == "det-high-priority"
    assert sent_payload["priority_score"] == 0.89


@patch("requests.post")
def test_webhook_dispatch_suppressed_for_low_priority(mock_post):
    """Verify detections with priority_score <= 0.85 are suppressed."""
    detection = {
        "id": "det-low-priority",
        "classification": "INDUSTRIAL_BUILDING",
        "confidence": 0.80,
        "priority_score": 0.65,  # <= 0.85
    }

    results = dispatch_high_priority_alert(
        detection, webhook_urls=["https://siem.defense.internal"]
    )
    assert results == []
    mock_post.assert_not_called()


def test_prune_local_raw_rasters_retention(tmp_path):
    """Verify files older than 7 days are deleted while newer files are preserved."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # 1. Expired file: 10 days old
    old_file = raw_dir / "sentinel2_tile_old.tif"
    old_file.write_bytes(b"OLD_RAW_TIFF_CONTENT" * 100)
    ten_days_ago = time.time() - (10 * 86400)
    os.utime(str(old_file), (ten_days_ago, ten_days_ago))

    # 2. Fresh file: 2 days old
    new_file = raw_dir / "sentinel2_tile_recent.tif"
    new_file.write_bytes(b"RECENT_RAW_TIFF_CONTENT" * 100)
    two_days_ago = time.time() - (2 * 86400)
    os.utime(str(new_file), (two_days_ago, two_days_ago))

    # Run pruning with 7-day retention
    report = prune_local_raw_rasters(raw_dir, retention_days=7, dry_run=False)

    assert report.scanned_count == 2
    assert report.pruned_count == 1
    assert report.retained_count == 1
    assert report.bytes_freed > 0

    # Old file must be deleted, new file must still exist
    assert not old_file.exists()
    assert new_file.exists()


def test_prune_dry_run_preserves_files(tmp_path):
    """Verify dry_run identifies candidates without unlinking them."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    expired_file = raw_dir / "expired_candidate.tif"
    expired_file.write_bytes(b"DATA" * 50)
    nine_days_ago = time.time() - (9 * 86400)
    os.utime(str(expired_file), (nine_days_ago, nine_days_ago))

    report = prune_local_raw_rasters(raw_dir, retention_days=7, dry_run=True)

    assert report.pruned_count == 1
    # File must still exist because dry_run was active
    assert expired_file.exists()


def test_run_pruning_cycle_end_to_end(tmp_path):
    """Test full cycle execution returns valid metrics summary."""
    raw_dir = tmp_path / "data_raw"
    raw_dir.mkdir()

    summary = run_pruning_cycle(retention_days=7, local_raw_dir=str(raw_dir), dry_run=True)
    assert summary["retention_days"] == 7
    assert summary["dry_run"] is True
    assert "local_storage" in summary
    assert "total_pruned_count" in summary
