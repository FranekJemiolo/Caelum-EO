"""Unit tests for Phase 6 / Version 4: Tactical Edge Cursor-on-Target (CoT) Dispatcher.

Validates:
- Coordinate and elevation extraction across GeoJSON primitives
- MIL-STD-2525 symbol code mapping for military infrastructure
- Cursor-on-Target (CoT) XML schema v2.0 serialization
- Network socket broadcast dispatch (UDP / TCP mocks)
- FastApi REST endpoints for CoT preview and tactical edge broadcast
- Automated CoT dispatch trigger upon detection verification
"""

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.cot_dispatcher import CoTDispatcher, cot_dispatcher
from src.api.main import app
from src.api.models import ReviewPayload, ReviewStatus
from src.api.service import triage_service


@pytest.fixture
def sample_detection_record():
    """Sample verified detection record for CoT testing."""
    return {
        "id": "det-cot-001",
        "classification": "RADAR_DOME",
        "verified_class": "RADAR_DOME",
        "confidence": 0.95,
        "priority_score": 0.92,
        "area_sq_meters": 540.0,
        "zone_id": "suwalki_corridor",
        "reviewer_notes": "Early warning radar installation verified.",
        "reviewed_by": "analyst_viper",
        "elevation_msl": 185.4,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [23.230, 54.140, 185.0],
                    [23.235, 54.140, 186.0],
                    [23.235, 54.145, 185.5],
                    [23.230, 54.145, 185.0],
                    [23.230, 54.140, 185.0],
                ]
            ],
        },
    }


def test_mil_std_2525_mapping():
    """Verify MIL-STD-2525 symbol codes are accurately mapped for military classes."""
    dispatcher = CoTDispatcher()
    assert dispatcher.get_mil_std_code("RADAR_DOME") == "a-h-G-U-C-R"
    assert dispatcher.get_mil_std_code("SAM_SITE") == "a-h-G-U-C-M"
    assert dispatcher.get_mil_std_code("RUNWAY_TAXIWAY") == "a-f-G-I-A"
    assert dispatcher.get_mil_std_code("LOGISTICS_DEPOT") == "a-h-G-I-S"
    assert dispatcher.get_mil_std_code("DEFENSE_REVETMENT") == "a-h-G-I-M"
    assert dispatcher.get_mil_std_code("INDUSTRIAL_BUILDING") == "a-h-G-I-B"
    assert dispatcher.get_mil_std_code("UNKNOWN_ANOMALY") == "a-h-G-I"


def test_cot_coordinate_extraction(sample_detection_record):
    """Verify centroid and elevation extraction from GeoJSON polygons."""
    dispatcher = CoTDispatcher()
    lon, lat, ele = dispatcher.extract_coordinates(sample_detection_record)

    assert 23.23 <= lon <= 23.235
    assert 54.14 <= lat <= 54.145
    assert ele == 185.4  # Matches explicit elevation_msl


def test_cot_xml_serialization(sample_detection_record):
    """Verify CoT XML v2.0 serialization matches DoD and ATAK standards."""
    dispatcher = CoTDispatcher()
    xml_str, uid, cot_type, callsign = dispatcher.serialize_cot_xml(sample_detection_record)

    assert uid == "caelum-det-cot-001"
    assert cot_type == "a-h-G-U-C-R"
    assert "RADAR-DOME" in callsign

    # Validate XML schema parseability
    root = ET.fromstring(xml_str)
    assert root.tag == "event"
    assert root.attrib["version"] == "2.0"
    assert root.attrib["uid"] == uid
    assert root.attrib["type"] == "a-h-G-U-C-R"
    assert root.attrib["how"] == "m-g"

    point = root.find("point")
    assert point is not None
    assert "lat" in point.attrib
    assert "lon" in point.attrib
    assert point.attrib["hae"] == "185.4"

    detail = root.find("detail")
    assert detail is not None
    contact = detail.find("contact")
    assert contact is not None
    assert contact.attrib["callsign"] == callsign

    remarks = detail.find("remarks")
    assert remarks is not None
    assert "RADAR_DOME" in remarks.text
    assert "suwalki_corridor" in remarks.text


def test_cot_socket_transmission(sample_detection_record):
    """Verify UDP and TCP socket transmission methods."""
    dispatcher = CoTDispatcher(tak_host="127.0.0.1", tak_port=8087)
    xml_str, _, _, _ = dispatcher.serialize_cot_xml(sample_detection_record)

    # Test UDP send mock
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock_cls.return_value.__enter__.return_value = mock_sock

        success_udp = dispatcher.send_socket_payload(xml_str, proto="udp")
        assert success_udp is True
        mock_sock.sendto.assert_called_once()

        # Test TCP send mock
        success_tcp = dispatcher.send_socket_payload(xml_str, proto="tcp")
        assert success_tcp is True
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 8087))
        mock_sock.sendall.assert_called_once()


def test_cot_api_endpoints(sample_detection_record):
    """Verify FastApi endpoints for CoT XML preview and tactical edge broadcast."""
    client = TestClient(app)

    # Authenticate as analyst
    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Register detection in service mock store
    det_id = "test-cot-target-01"
    sample_detection_record["id"] = det_id
    triage_service._mock_detections[det_id] = sample_detection_record

    # 1. Preview CoT XML
    prev_resp = client.get(f"/api/v1/cot/preview/{det_id}", headers=headers)
    assert prev_resp.status_code == 200
    assert "application/xml" in prev_resp.headers["content-type"]
    root = ET.fromstring(prev_resp.content)
    assert root.tag == "event"
    assert root.attrib["type"] == "a-h-G-U-C-R"

    # 2. Broadcast CoT to ATAK
    with patch.object(cot_dispatcher, "send_socket_payload", return_value=True):
        bcast_resp = client.post(f"/api/v1/cot/broadcast/{det_id}", headers=headers)
        assert bcast_resp.status_code == 200
        data = bcast_resp.json()
        assert data["status"] == "DISPATCHED"
        assert data["detection_id"] == det_id
        assert data["mil_std_2525_type"] == "a-h-G-U-C-R"
        assert "xml_payload" in data


def test_automated_cot_dispatch_on_verification():
    """Verify that submitting a VERIFIED review triggers automated CoT dispatch."""
    det_id = "det-verify-cot-auto"
    triage_service._mock_detections[det_id] = {
        "id": det_id,
        "classification": "SAM_SITE",
        "confidence": 0.93,
        "coordinates": [23.24, 54.15, 160.0],
        "review_status": "PENDING_REVIEW",
        "priority_score": 0.88,
        "zone_id": "suwalki_corridor",
    }

    payload = ReviewPayload(
        review_status=ReviewStatus.VERIFIED,
        verified_class=None,
        reviewer_notes="Confirmed active mobile air defense battery.",
        reviewed_by="analyst_viper",
    )

    with patch.object(cot_dispatcher, "dispatch_detection") as mock_dispatch:
        review_res = triage_service.submit_review(det_id, payload)
        assert review_res is not None
        assert review_res.review_status == ReviewStatus.VERIFIED
        mock_dispatch.assert_called_once()
        record_called = mock_dispatch.call_args[0][0]
        assert record_called["id"] == det_id
        assert record_called["classification"] == "SAM_SITE"
