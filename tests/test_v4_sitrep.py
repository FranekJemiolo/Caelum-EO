"""Unit tests for Phase 6 / Version 4: Generative SITREPs (Local LLM Integration).

Validates:
- Aggregation of VERIFIED detections over lookback windows
- Strict military prompt engineering (NATO doctrine, target breakdown)
- Air-gapped deterministic brief fallback when Ollama is offline
- Ollama mock LLM inference integration
- REST endpoints for SITREP archive, generation, and analyst modifications
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.sitrep_generator import SITREPGenerator


@pytest.fixture
def mock_aggregated_data():
    """Sample aggregated intelligence data for SITREP testing."""
    return {
        "hours_lookback": 24,
        "window_start": "2026-09-28T10:00:00Z",
        "window_end": "2026-09-29T10:00:00Z",
        "total_targets": 4,
        "high_priority_count": 2,
        "total_area_sq_m": 8450.0,
        "class_distribution": {"RADAR_DOME": 1, "SAM_SITE": 1, "LOGISTICS_DEPOT": 2},
        "zone_distribution": {"suwalki_corridor": 3, "kaliningrad_border": 1},
        "sample_targets": [
            {
                "id": "det-1",
                "classification": "RADAR_DOME",
                "priority_score": 0.94,
                "area_sq_meters": 450.0,
                "zone_id": "suwalki_corridor",
            },
            {
                "id": "det-2",
                "classification": "SAM_SITE",
                "priority_score": 0.91,
                "area_sq_meters": 1200.0,
                "zone_id": "suwalki_corridor",
            },
        ],
    }


def test_sitrep_generator_prompt_formatting(mock_aggregated_data):
    """Verify military doctrine prompt formatting includes counts and categories."""
    generator = SITREPGenerator(ollama_url="http://mock-ollama:11434")

    prompt = generator.construct_military_prompt(mock_aggregated_data)

    assert "MILITARY SITUATION REPORT (SITREP)" in prompt
    assert "RADAR_DOME: 1" in prompt
    assert "SAM_SITE: 1" in prompt
    assert "Total Verified Targets: 4" in prompt
    assert "suwalki_corridor: 3" in prompt


def test_sitrep_generator_deterministic_fallback(mock_aggregated_data):
    """Verify air-gapped deterministic summary generator when LLM is unavailable."""
    generator = SITREPGenerator(ollama_url="http://mock-ollama:11434")

    brief = generator.generate_analytical_fallback_sitrep(mock_aggregated_data)

    assert "MILITARY SITUATION REPORT (SITREP)" in brief
    assert "EXECUTIVE SUMMARY & THREAT LEVEL" in brief
    assert "SECTOR-BY-SECTOR DISPOSITION" in brief
    assert "RADAR DOME" in brief
    assert "PATTERN OF LIFE (PoL) DYNAMICS" in brief
    assert "COMMANDER'S ACTIONABLE RECOMMENDATIONS" in brief


def test_sitrep_generator_generate_with_mock_ollama(mock_aggregated_data):
    """Verify SITREP generation querying mock Ollama server."""
    generator = SITREPGenerator(
        ollama_url="http://mock-ollama:11434", model_name="llama3:8b-instruct"
    )

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200
    mock_ollama_resp.json.return_value = {
        "response": "CLASSIFIED // NOFORN // REL TO NATO\n\n1. SITUATION: Logistics build-up confirmed in Sector 4.\n2. SAM Site detected at 54.16N, 23.25E."
    }

    with patch("httpx.Client.post", return_value=mock_ollama_resp):
        with patch.object(
            generator, "aggregate_verified_detections", return_value=mock_aggregated_data
        ):
            report = generator.generate_sitrep(
                hours_lookback=24, zone_id="suwalki_corridor", model_name="llama3:8b-instruct"
            )

            assert report["title"].startswith("DAILY SITREP:")
            assert "CLASSIFIED // NOFORN" in report["sitrep_content"]
            assert report["target_count"] == 4
            assert report["model_name"] == "llama3:8b-instruct"


def test_sitrep_generator_fallback_on_network_error(mock_aggregated_data):
    """Verify graceful degradation to deterministic brief if Ollama network call fails."""
    generator = SITREPGenerator(ollama_url="http://mock-ollama:11434")

    with patch("httpx.Client.post", side_effect=Exception("Connection refused")):
        with patch.object(
            generator, "aggregate_verified_detections", return_value=mock_aggregated_data
        ):
            report = generator.generate_sitrep(hours_lookback=24)

            assert "DAILY SITREP:" in report["title"]
            assert "MILITARY SITUATION REPORT" in report["sitrep_content"]
            assert report["status"] == "ANALYTICAL_FALLBACK"


def test_sitrep_api_endpoints():
    """Verify REST endpoints for SITREP retrieval, generation, and updates."""
    client = TestClient(app)

    # 0. Authenticate as analyst
    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Generate SITREP via API
    gen_payload = {
        "hours_lookback": 24,
        "zone_id": "suwalki_corridor",
        "model": "llama3:8b-instruct",
    }

    resp = client.post("/api/v1/sitreps/generate", json=gen_payload, headers=headers)
    assert resp.status_code == 200
    created = resp.json()
    assert "id" in created
    assert "sitrep_content" in created
    assert created["target_count"] >= 0
    report_id = created["id"]

    # 2. List SITREPs
    resp_list = client.get("/api/v1/sitreps", headers=headers)
    assert resp_list.status_code == 200
    reports = resp_list.json()
    assert isinstance(reports, list)
    assert any(r["id"] == report_id for r in reports)

    # 3. Get single SITREP by ID
    resp_single = client.get(f"/api/v1/sitreps/{report_id}", headers=headers)
    assert resp_single.status_code == 200
    assert resp_single.json()["id"] == report_id

    # 4. Update SITREP content (Analyst modification)
    update_payload = {
        "title": "UPDATED SITREP - Sector Alpha",
        "sitrep_content": "Analyst verified revised assessment notes.",
    }
    resp_update = client.put(f"/api/v1/sitreps/{report_id}", json=update_payload, headers=headers)
    assert resp_update.status_code == 200
    updated = resp_update.json()
    assert updated["title"] == "UPDATED SITREP - Sector Alpha"
    assert updated["sitrep_content"] == "Analyst verified revised assessment notes."

    # 5. Invalid report ID returns 404
    resp_not_found = client.get("/api/v1/sitreps/non-existent-id", headers=headers)
    assert resp_not_found.status_code == 404
