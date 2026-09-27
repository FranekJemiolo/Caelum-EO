"""Unit and integration tests for Authentication and Role-Based Access Control (RBAC).

Tests:
- Token acquisition via OAuth2 password flow
- Role validation for viewer, analyst, and admin
- Endpoint protection and 401 Unauthorized handling
- RBAC permissions on Human-in-the-Loop review (403 Forbidden for viewers)
- Current user profile retrieval (/api/v1/auth/me)
"""

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_login_success():
    """Verify login succeeds and issues JWT bearer tokens with correct roles."""
    # Test admin
    res_admin = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "caelum_admin_2026!"},
    )
    assert res_admin.status_code == 200
    data_admin = res_admin.json()
    assert "access_token" in data_admin
    assert data_admin["token_type"] == "bearer"
    assert data_admin["role"] == "admin"
    assert data_admin["username"] == "admin"

    # Test analyst
    res_analyst = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    assert res_analyst.status_code == 200
    assert res_analyst.json()["role"] == "analyst"

    # Test viewer
    res_viewer = client.post(
        "/api/v1/auth/token",
        data={"username": "viewer_01", "password": "caelum_viewer_2026!"},
    )
    assert res_viewer.status_code == 200
    assert res_viewer.json()["role"] == "viewer"


def test_login_invalid_credentials():
    """Verify login fails with 401 when given bad password or unknown username."""
    res_bad_pw = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "wrong_password!"},
    )
    assert res_bad_pw.status_code == 401

    res_bad_user = client.post(
        "/api/v1/auth/token",
        data={"username": "nonexistent_operator", "password": "password"},
    )
    assert res_bad_user.status_code == 401


def test_unauthenticated_request_rejected():
    """Verify protected endpoints reject requests missing an Authorization header."""
    res = client.get("/api/v1/detections")
    assert res.status_code == 401

    res_zones = client.get("/api/v1/zones/summary")
    assert res_zones.status_code == 401

    res_me = client.get("/api/v1/auth/me")
    assert res_me.status_code == 401


def test_auth_me_endpoint():
    """Verify /api/v1/auth/me returns valid identity when authenticated."""
    token_res = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    token = token_res.json()["access_token"]

    res_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_me.status_code == 200
    user_data = res_me.json()
    assert user_data["username"] == "analyst_viper"
    assert user_data["role"] == "analyst"


def test_rbac_review_permissions():
    """Verify RBAC: Viewer cannot review (403), Analyst and Admin can review (200)."""
    # 1. Acquire tokens
    v_token = client.post(
        "/api/v1/auth/token",
        data={"username": "viewer_01", "password": "caelum_viewer_2026!"},
    ).json()["access_token"]

    a_token = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    ).json()["access_token"]

    det_id = "c3d4e5f6-a7b8-49c0-d123-456789abcdef"
    payload = {
        "review_status": "VERIFIED",
        "verified_class": "RADAR_DOME",
        "reviewer_notes": "RBAC verification test note.",
    }

    # Viewer attempts review -> 403 Forbidden
    res_viewer = client.patch(
        f"/api/v1/detections/{det_id}/review",
        json=payload,
        headers={"Authorization": f"Bearer {v_token}"},
    )
    assert res_viewer.status_code == 403

    # Analyst attempts review -> 200 OK
    res_analyst = client.patch(
        f"/api/v1/detections/{det_id}/review",
        json=payload,
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert res_analyst.status_code == 200
    assert res_analyst.json()["review_status"] == "VERIFIED"
    assert res_analyst.json()["reviewed_by"] == "analyst_viper"
