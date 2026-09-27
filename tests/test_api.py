"""Unit and integration tests for Caelum-EO Triage & Analytical APIs."""

from fastapi.testclient import TestClient

from src.api.auth import create_access_token
from src.api.main import app

client = TestClient(app)
admin_token = create_access_token({"sub": "admin", "role": "admin"})
client.headers = {"Authorization": f"Bearer {admin_token}"}


def test_health_check():
    """Verify system health liveness probe."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "caelum-eo-api"
    assert data["repository"] == "github.com/FranekJemiolo/Caelum-EO"


def test_get_detections_geojson():
    """Verify detection retrieval as standard GeoJSON FeatureCollection."""
    response = client.get("/api/v1/detections")
    assert response.status_code == 200
    geojson = response.json()
    assert geojson["type"] == "FeatureCollection"
    assert "features" in geojson
    assert len(geojson["features"]) > 0

    first_feat = geojson["features"][0]
    assert first_feat["type"] == "Feature"
    assert "geometry" in first_feat
    assert "properties" in first_feat
    props = first_feat["properties"]
    assert "classification" in props
    assert "confidence" in props
    assert "priority_score" in props


def test_get_detections_filtering():
    """Test filtering detections by classification and confidence."""
    # Filter by RADAR_DOME
    response = client.get("/api/v1/detections?classification=RADAR_DOME")
    assert response.status_code == 200
    features = response.json()["features"]
    assert all(f["properties"]["classification"] == "RADAR_DOME" for f in features)

    # Filter by high confidence
    response = client.get("/api/v1/detections?min_confidence=0.95")
    assert response.status_code == 200
    features = response.json()["features"]
    assert all(f["properties"]["confidence"] >= 0.95 for f in features)


def test_get_zones_summary():
    """Verify aggregated metrics across strategic geographic surveillance zones."""
    response = client.get("/api/v1/zones/summary")
    assert response.status_code == 200
    zones = response.json()
    assert isinstance(zones, list)
    assert len(zones) >= 1

    suwalki = next((z for z in zones if "SUWALKI" in z["id"]), None)
    assert suwalki is not None
    assert suwalki["alert_level"] in ["HIGH", "ELEVATED", "NORMAL"]
    assert "total_detections" in suwalki
    assert "new_detections_24h" in suwalki
    assert "classification_breakdown" in suwalki


def test_get_triage_queue_ranking():
    """Verify pending detections are sorted in descending order of priority score."""
    response = client.get("/api/v1/triage/queue?limit=10")
    assert response.status_code == 200
    queue = response.json()
    assert isinstance(queue, list)
    assert len(queue) > 0

    # Ensure monotonic non-increasing priority scores
    scores = [float(item["priority_score"]) for item in queue]
    assert scores == sorted(scores, reverse=True)
    assert all(item["review_status"] == "PENDING_REVIEW" for item in queue)


def test_get_imagery_metadata_and_chips():
    """Verify retrieval of satellite chip URLs and binary streaming responses."""
    det_id = "a1b2c3d4-e5f6-47a8-b901-23456789abcd"

    # 1. Metadata endpoint
    res_meta = client.get(f"/api/v1/detections/{det_id}/imagery")
    assert res_meta.status_code == 200
    meta = res_meta.json()
    assert meta["detection_id"] == det_id
    assert "/imagery/t0" in meta["t0_image_url"]
    assert "/imagery/t1" in meta["t1_image_url"]
    assert "/imagery/mask" in meta["mask_image_url"]

    # 2. Binary image streaming endpoints
    for layer in ["t0", "t1", "mask"]:
        res_img = client.get(f"/api/v1/detections/{det_id}/imagery/{layer}")
        assert res_img.status_code == 200
        assert res_img.headers["content-type"] == "image/png"
        assert len(res_img.content) > 50  # Valid PNG byte stream


def test_imagery_404_and_400():
    """Verify proper HTTP error codes for invalid detection IDs and layer types."""
    res_404 = client.get("/api/v1/detections/nonexistent-uuid/imagery")
    assert res_404.status_code == 404

    res_400 = client.get(
        "/api/v1/detections/a1b2c3d4-e5f6-47a8-b901-23456789abcd/imagery/invalid_layer"
    )
    assert res_400.status_code == 400


def test_patch_review_hitl_reclassification():
    """Test full Human-in-the-Loop review and reclassification workflow."""
    det_id = "b2c3d4e5-f6a7-48b9-c012-3456789abcde"

    # 1. Submit reclassification to DEFENSE_REVETMENT
    payload = {
        "review_status": "MISCLASSIFIED",
        "verified_class": "DEFENSE_REVETMENT",
        "reviewer_notes": "Ground verification confirms revetment bunker, not depot.",
        "reviewed_by": "analyst_viper_01",
    }
    response = client.patch(f"/api/v1/detections/{det_id}/review", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == det_id
    assert data["review_status"] == "MISCLASSIFIED"
    assert data["verified_class"] == "DEFENSE_REVETMENT"
    assert data["reviewed_by"] == "analyst_viper_01"
    assert "priority_score" in data

    # 2. Confirm updated state in exploration endpoint
    res_check = client.get("/api/v1/detections?review_status=MISCLASSIFIED")
    assert res_check.status_code == 200
    features = res_check.json()["features"]
    assert any(f["id"] == det_id for f in features)


def test_patch_review_false_positive():
    """Test marking anomaly as false positive drops priority score to 0."""
    det_id = "e5f6a7b8-c9d0-41e2-f345-6789abcdef01"
    payload = {
        "review_status": "FALSE_POSITIVE",
        "verified_class": None,
        "reviewer_notes": "Agricultural tilling anomaly; no structural concrete.",
        "reviewed_by": "analyst_eagle_02",
    }
    response = client.patch(f"/api/v1/detections/{det_id}/review", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["review_status"] == "FALSE_POSITIVE"
    assert data["priority_score"] == 0.0


def test_login_auth_flow():
    """Verify OAuth2 password token endpoint."""
    res_ok = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "caelum_admin_2026!"},
    )
    assert res_ok.status_code == 200
    token_data = res_ok.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["role"] == "admin"

    res_fail = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "wrong_password"},
    )
    assert res_fail.status_code == 401


def test_auth_rbac_forbidden():
    """Verify viewer role cannot submit reviews (403 Forbidden)."""
    viewer_token = create_access_token({"sub": "viewer_01", "role": "viewer"})
    viewer_client = TestClient(app)
    viewer_client.headers = {"Authorization": f"Bearer {viewer_token}"}

    det_id = "a1b2c3d4-e5f6-47a8-b901-23456789abcd"
    res = viewer_client.patch(
        f"/api/v1/detections/{det_id}/review",
        json={"review_status": "VERIFIED"},
    )
    assert res.status_code == 403


def test_service_sql_mock_paths():
    """Verify TriageService execution when database connection is active."""
    from unittest.mock import MagicMock

    from src.api.service import ReviewPayload, ReviewStatus, TriageService

    svc = TriageService()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.closed = False
    svc._conn = mock_conn

    # 1. get_detections SQL branch
    mock_cur.fetchall.return_value = [
        {
            "id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
            "geometry": {"type": "Polygon", "coordinates": []},
            "classification": "RADAR_DOME",
            "confidence": 0.95,
            "area_sq_meters": 1000.0,
            "baseline_timestamp": None,
            "detection_timestamp": None,
            "sensor_source": "Sentinel-2",
            "zone_id": "ZONE-SUWALKI-CORRIDOR",
            "review_status": "PENDING_REVIEW",
            "verified_class": None,
            "priority_score": 0.9,
            "reviewer_notes": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "baseline_chip_path": None,
            "detection_chip_path": None,
            "stac_metadata": {},
        }
    ]
    dets = svc.get_detections(limit=1)
    assert len(dets["features"]) == 1

    # 2. get_zones_summary SQL branch
    mock_cur.fetchall.return_value = [
        {
            "id": "ZONE-SUWALKI-CORRIDOR",
            "name": "Suwalki Gap",
            "alert_level": "HIGH",
            "boundary": {"type": "Polygon", "coordinates": []},
            "total_detections": 10,
            "new_detections_24h": 2,
            "new_detections_7d": 5,
            "high_priority_count": 3,
            "classification_breakdown": {"RADAR_DOME": 3},
        }
    ]
    zones = svc.get_zones_summary()
    assert len(zones) == 1
    assert zones[0].id == "ZONE-SUWALKI-CORRIDOR"

    # 3. get_triage_queue SQL branch
    mock_cur.fetchall.return_value = [
        {
            "id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
            "geometry": {"type": "Polygon", "coordinates": []},
            "classification": "RADAR_DOME",
            "confidence": 0.95,
            "area_sq_meters": 1000.0,
            "detection_timestamp": None,
            "sensor_source": "Sentinel-2",
            "zone_id": "ZONE-SUWALKI-CORRIDOR",
            "review_status": "PENDING_REVIEW",
            "priority_score": 0.9,
            "baseline_chip_path": None,
            "detection_chip_path": None,
        }
    ]
    queue = svc.get_triage_queue(limit=5)
    assert len(queue) == 1

    # 4. get_detection_by_id SQL branch
    mock_cur.fetchone.return_value = {
        "id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
        "geometry": {"type": "Polygon", "coordinates": []},
        "classification": "RADAR_DOME",
        "confidence": 0.95,
        "area_sq_meters": 1000.0,
        "baseline_timestamp": None,
        "detection_timestamp": None,
        "sensor_source": "Sentinel-2",
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "review_status": "PENDING_REVIEW",
        "verified_class": None,
        "priority_score": 0.9,
        "reviewer_notes": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "baseline_chip_path": None,
        "detection_chip_path": None,
        "stac_metadata": {},
    }
    det = svc.get_detection_by_id("a1b2c3d4-e5f6-47a8-b901-23456789abcd")
    assert det is not None

    # 5. submit_review SQL branch
    rev_res = svc.submit_review(
        "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
        ReviewPayload(review_status=ReviewStatus.VERIFIED, reviewer_notes="Confirmed"),
    )
    assert rev_res is not None
    assert rev_res.review_status == ReviewStatus.VERIFIED
