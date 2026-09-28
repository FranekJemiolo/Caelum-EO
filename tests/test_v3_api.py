"""Unit and Integration Tests for Version 3 Analyst & Admin APIs.

Tests:
- Dynamic Configuration CRUD (admin role enforcement)
- Threaded Analyst Comments
- Detection Lifecycle Audit Log
- Saved Filter Preset Management
- Intelligence GeoJSON & CSV Export Engine
"""

import json
from typing import Dict

from fastapi.testclient import TestClient

from src.api.auth import create_access_token
from src.api.main import app

client = TestClient(app)


def get_auth_header(role: str = "analyst", username: str = "analyst_viper") -> Dict[str, str]:
    token = create_access_token(
        data={"sub": username, "role": role, "id": "00000000-0000-0000-0000-000000000002"}
    )
    return {"Authorization": f"Bearer {token}"}


def test_admin_config_rbac():
    # Viewer should be forbidden
    viewer_headers = get_auth_header(role="viewer", username="viewer_01")
    res = client.get("/api/v1/admin/config", headers=viewer_headers)
    assert res.status_code == 403

    # Analyst should be forbidden
    analyst_headers = get_auth_header(role="analyst", username="analyst_viper")
    res = client.get("/api/v1/admin/config", headers=analyst_headers)
    assert res.status_code == 403

    # Admin should succeed
    admin_headers = get_auth_header(role="admin", username="admin")
    res = client.get("/api/v1/admin/config", headers=admin_headers)
    assert res.status_code == 200
    configs = res.json()
    assert isinstance(configs, list)
    keys = [c["key"] for c in configs]
    assert "ml_confidence_threshold" in keys
    assert "target_geofences" in keys


def test_admin_config_crud():
    admin_headers = get_auth_header(role="admin", username="admin")

    # Get single key
    res = client.get("/api/v1/admin/config/ml_confidence_threshold", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["key"] == "ml_confidence_threshold"

    # 404 on missing key
    res = client.get("/api/v1/admin/config/non_existent_key_xyz", headers=admin_headers)
    assert res.status_code == 404

    # Update key
    res = client.put(
        "/api/v1/admin/config/ml_confidence_threshold",
        json={"value": "0.85", "description": "Tuned threshold to reduce false alarms"},
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.json()["value"] == "0.85"

    # Verify updated
    res = client.get("/api/v1/admin/config/ml_confidence_threshold", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["value"] == "0.85"

    # Post new key
    res = client.post(
        "/api/v1/admin/config",
        json={"key": "test_alert_cooldown", "value": "120", "description": "Cooldown in seconds"},
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.json()["key"] == "test_alert_cooldown"
    assert res.json()["value"] == "120"


def test_analyst_comments_workflow():
    analyst_headers = get_auth_header(role="analyst", username="analyst_viper")
    viewer_headers = get_auth_header(role="viewer", username="viewer_01")
    detection_id = "a1b2c3d4-e5f6-47a8-b901-23456789abcd"

    # Viewer cannot post comment
    res = client.post(
        f"/api/v1/detections/{detection_id}/comments",
        json={"comment": "Unauthorized comment"},
        headers=viewer_headers,
    )
    assert res.status_code == 403

    # Analyst can post comment
    comment_text = "Verified SAR coherence change matching new concrete apron pouring."
    res = client.post(
        f"/api/v1/detections/{detection_id}/comments",
        json={"comment": comment_text},
        headers=analyst_headers,
    )
    assert res.status_code == 201
    created_comment = res.json()
    assert created_comment["comment"] == comment_text
    assert created_comment["username"] == "analyst_viper"
    assert created_comment["detection_id"] == detection_id

    # Retrieve comments
    res = client.get(
        f"/api/v1/detections/{detection_id}/comments",
        headers=analyst_headers,
    )
    assert res.status_code == 200
    comments = res.json()
    assert any(c["comment"] == comment_text for c in comments)


def test_detection_audit_history():
    analyst_headers = get_auth_header(role="analyst", username="analyst_viper")
    detection_id = "b2c3d4e5-f6a7-48b9-c012-3456789abcde"

    # Submit review transition
    review_res = client.patch(
        f"/api/v1/detections/{detection_id}/review",
        json={
            "review_status": "VERIFIED",
            "verified_class": "LOGISTICS_DEPOT",
            "reviewer_notes": "Ground truth confirmed via multi-angle SAR imagery.",
            "reviewed_by": "analyst_viper",
        },
        headers=analyst_headers,
    )
    assert review_res.status_code == 200

    # Check audit trail
    res = client.get(
        f"/api/v1/detections/{detection_id}/audit",
        headers=analyst_headers,
    )
    assert res.status_code == 200
    trail = res.json()
    assert len(trail) >= 1
    latest_event = trail[-1]
    assert latest_event["detection_id"] == detection_id
    assert latest_event["new_state"] == "VERIFIED"
    assert latest_event["username"] == "analyst_viper"


def test_saved_filters_workflow():
    analyst_headers = get_auth_header(role="analyst", username="analyst_viper")

    filter_data = {
        "name": "High-Confidence Radars",
        "filter_json": {
            "classification": "RADAR_DOME",
            "min_confidence": 0.90,
            "zone_id": "ZONE-SUWALKI-CORRIDOR",
        },
    }

    # Create saved filter
    res = client.post("/api/v1/saved-filters", json=filter_data, headers=analyst_headers)
    assert res.status_code == 201
    created_filter = res.json()
    filter_id = created_filter["id"]
    assert created_filter["name"] == "High-Confidence Radars"
    assert created_filter["filter_json"]["classification"] == "RADAR_DOME"

    # List saved filters
    res = client.get("/api/v1/saved-filters", headers=analyst_headers)
    assert res.status_code == 200
    filters = res.json()
    assert any(f["id"] == filter_id for f in filters)

    # Delete saved filter
    del_res = client.delete(f"/api/v1/saved-filters/{filter_id}", headers=analyst_headers)
    assert del_res.status_code == 204

    # Verify deleted
    res = client.get("/api/v1/saved-filters", headers=analyst_headers)
    assert res.status_code == 200
    assert not any(f["id"] == filter_id for f in res.json())


def test_export_engine_geojson_and_csv():
    analyst_headers = get_auth_header(role="analyst", username="analyst_viper")

    # 1. GeoJSON export via GET
    res = client.get("/api/v1/export?format=geojson", headers=analyst_headers)
    assert res.status_code == 200
    assert "application/geo+json" in res.headers["content-type"]
    assert "caelum_detections_export.geojson" in res.headers["content-disposition"]
    data = json.loads(res.content)
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0

    # 2. CSV export via GET
    res_csv = client.get("/api/v1/export?format=csv", headers=analyst_headers)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "caelum_detections_export.csv" in res_csv.headers["content-disposition"]
    csv_text = res_csv.content.decode("utf-8")
    lines = csv_text.strip().split("\n")
    assert len(lines) >= 2
    assert "id,classification,confidence" in lines[0]
    assert "latitude,longitude" in lines[0]

    # 3. Export specific detection IDs via POST
    detection_id = "a1b2c3d4-e5f6-47a8-b901-23456789abcd"
    res_post = client.post(
        "/api/v1/export",
        json={"detection_ids": [detection_id], "format": "geojson"},
        headers=analyst_headers,
    )
    assert res_post.status_code == 200
    post_data = json.loads(res_post.content)
    assert len(post_data["features"]) == 1
    assert post_data["features"][0]["id"] == detection_id

    # 4. Invalid format
    res_bad = client.get("/api/v1/export?format=xml", headers=analyst_headers)
    assert res_bad.status_code == 400


def test_triage_service_database_branches(monkeypatch):
    """Test PostGIS-connected branches in TriageService via mocked database cursor."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from src.api.service import triage_service

    now = datetime.now(timezone.utc)

    # 1. Test get_configurations with db
    mock_cur = MagicMock()
    mock_cur.description = [
        ("id",),
        ("key",),
        ("value",),
        ("description",),
        ("updated_by",),
        ("updated_at",),
    ]
    mock_cur.fetchall.return_value = [
        (
            1,
            "ml_confidence_threshold",
            "0.75",
            "Test description",
            "00000000-0000-0000-0000-000000000001",
            now,
        )
    ]
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    monkeypatch.setattr(triage_service, "get_connection", lambda: mock_conn)
    configs = triage_service.get_configurations()
    assert len(configs) == 1
    assert configs[0]["key"] == "ml_confidence_threshold"

    # 2. Test get_configuration with db
    mock_cur.fetchone.return_value = (
        1,
        "ml_confidence_threshold",
        "0.75",
        "Test description",
        "00000000-0000-0000-0000-000000000001",
        now,
    )
    conf = triage_service.get_configuration("ml_confidence_threshold")
    assert conf is not None
    assert conf["value"] == "0.75"

    # 3. Test set_configuration with db
    mock_cur.fetchone.return_value = (
        1,
        "ml_confidence_threshold",
        "0.80",
        "Updated description",
        "00000000-0000-0000-0000-000000000001",
        now,
    )
    saved_conf = triage_service.set_configuration("ml_confidence_threshold", "0.80")
    assert saved_conf["value"] == "0.80"

    # 4. Test comments with db
    mock_cur.description = [
        ("id",),
        ("detection_id",),
        ("user_id",),
        ("username",),
        ("comment",),
        ("created_at",),
    ]
    mock_cur.fetchall.return_value = [
        ("c1", "a1b2c3d4-e5f6-47a8-b901-23456789abcd", "u1", "analyst_viper", "DB comment", now)
    ]
    comments = triage_service.get_comments("a1b2c3d4-e5f6-47a8-b901-23456789abcd")
    assert len(comments) == 1
    assert comments[0]["comment"] == "DB comment"

    mock_cur.fetchone.return_value = (
        "c2",
        "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
        "u1",
        "analyst_viper",
        "New DB comment",
        now,
    )
    new_comment = triage_service.add_comment(
        "a1b2c3d4-e5f6-47a8-b901-23456789abcd", "New DB comment", "analyst_viper"
    )
    assert new_comment["comment"] == "New DB comment"

    # 5. Test detection audit trail with db
    mock_cur.description = [
        ("id",),
        ("detection_id",),
        ("previous_state",),
        ("new_state",),
        ("user_id",),
        ("username",),
        ("note",),
        ("timestamp",),
    ]
    mock_cur.fetchall.return_value = [
        ("a1", "d1", "PENDING_REVIEW", "VERIFIED", "u1", "analyst_viper", "Note", now)
    ]
    trail = triage_service.get_detection_audit_trail("d1")
    assert len(trail) == 1
    assert trail[0]["new_state"] == "VERIFIED"

    mock_cur.fetchone.return_value = (
        "a2",
        "d1",
        "PENDING_REVIEW",
        "MISCLASSIFIED",
        "u1",
        "analyst_viper",
        "Note",
        now,
    )
    audit_rec = triage_service.log_detection_audit(
        "d1", "PENDING_REVIEW", "MISCLASSIFIED", "analyst_viper"
    )
    assert audit_rec["new_state"] == "MISCLASSIFIED"

    # 6. Test saved filters with db
    mock_cur.description = [("id",), ("user_id",), ("name",), ("filter_json",), ("created_at",)]
    mock_cur.fetchall.return_value = [
        ("f1", "u1", "Filter 1", {"classification": "RADAR_DOME"}, now)
    ]
    filters = triage_service.get_saved_filters("u1")
    assert len(filters) == 1

    mock_cur.fetchone.return_value = ("f2", "u1", "Filter 2", {"confidence": 0.9}, now)
    new_filter = triage_service.create_saved_filter("u1", "Filter 2", {"confidence": 0.9})
    assert new_filter["name"] == "Filter 2"

    del_res = triage_service.delete_saved_filter("u1", "f2")
    assert del_res is True

    # 7. Test export with zone filter
    csv_str, m_type, filename = triage_service.export_detections(
        zone_id="ZONE-SUWALKI-CORRIDOR", format="csv"
    )
    assert m_type == "text/csv"
    assert "caelum_detections_export.csv" == filename
