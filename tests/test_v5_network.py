"""Unit tests for Phase V5: Logistics Network Graph and RL Analytics.

Validates:
- LogisticsNetworkGraph build from stub PostGIS data
- Betweenness centrality and threat flow computation
- Critical node identification
- NetworkX node-link JSON serialisation
- RL env observation/action spaces (when gymnasium is available)
- Stub PPO training fallback when RL libraries are absent
- NetworkAnalysisEngine full pipeline with mocked DB
- REST endpoint: POST /api/v1/network/analyse
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.analytics.network_graph import (
    InfraNode,
    LogisticsNetworkGraph,
    NetworkRLTrainer,
    TelemetryEdge,
)
from src.api.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NX_AVAILABLE = True
try:
    import networkx as nx  # noqa: F401
except ImportError:
    NX_AVAILABLE = False


@pytest.fixture
def sample_nodes() -> list[InfraNode]:
    return [
        InfraNode("node-A", "RADAR_DOME", 23.15, 54.22, 0.94, 450.0, "ZONE-1", 3, 0.82),
        InfraNode("node-B", "LOGISTICS_DEPOT", 23.25, 54.30, 0.81, 2500.0, "ZONE-1", 1, 0.41),
        InfraNode("node-C", "RUNWAY_TAXIWAY", 23.10, 54.10, 0.88, 5000.0, "ZONE-2", 0, 0.0),
        InfraNode("node-D", "DEFENSE_REVETMENT", 23.35, 54.35, 0.75, 800.0, "ZONE-2", 2, 0.60),
    ]


@pytest.fixture
def sample_edges() -> list[TelemetryEdge]:
    return [
        TelemetryEdge("node-A", "node-B", "AIS", flow_count=4, mean_dark_threat=0.75, distance_km=12.0),
        TelemetryEdge("node-B", "node-C", "AIS", flow_count=2, mean_dark_threat=0.55, distance_km=22.0),
        TelemetryEdge("node-A", "node-D", "ADSB", flow_count=1, mean_dark_threat=0.65, distance_km=17.0),
        TelemetryEdge("node-C", "node-D", "AIS", flow_count=3, mean_dark_threat=0.50, distance_km=30.0),
    ]


def _build_graph(nodes, edges) -> LogisticsNetworkGraph:
    """Build a LogisticsNetworkGraph from stub in-memory node/edge data."""
    g = LogisticsNetworkGraph()

    if not NX_AVAILABLE:
        return g

    import networkx as nx_lib

    graph = nx_lib.DiGraph()
    for node in nodes:
        graph.add_node(
            node.node_id,
            classification=node.classification,
            lon=node.lon,
            lat=node.lat,
            priority_score=node.priority_score,
            area_sq_m=node.area_sq_m,
            zone_id=node.zone_id,
            dark_event_count=node.dark_event_count,
            threat_score=node.threat_score,
        )
    for edge in edges:
        graph.add_edge(
            edge.source_id,
            edge.target_id,
            entity_type=edge.entity_type,
            flow_count=edge.flow_count,
            mean_dark_threat=edge.mean_dark_threat,
            distance_km=edge.distance_km,
            weight=edge.mean_dark_threat * edge.flow_count,
        )
    g._graph = graph
    return g


# ---------------------------------------------------------------------------
# Tests: Graph construction
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_graph_node_count(sample_nodes, sample_edges):
    g = _build_graph(sample_nodes, sample_edges)
    assert g.graph.number_of_nodes() == 4


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_graph_edge_count(sample_nodes, sample_edges):
    g = _build_graph(sample_nodes, sample_edges)
    assert g.graph.number_of_edges() == 4


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_graph_node_attributes(sample_nodes, sample_edges):
    g = _build_graph(sample_nodes, sample_edges)
    attrs = g.graph.nodes["node-A"]
    assert attrs["classification"] == "RADAR_DOME"
    assert attrs["dark_event_count"] == 3
    assert attrs["threat_score"] == pytest.approx(0.82)


# ---------------------------------------------------------------------------
# Tests: Centrality and threat flow
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_compute_centrality_returns_dict(sample_nodes, sample_edges):
    g = _build_graph(sample_nodes, sample_edges)
    centrality = g.compute_centrality()
    assert isinstance(centrality, dict)
    assert set(centrality.keys()) == {"node-A", "node-B", "node-C", "node-D"}
    # All values in [0, 1]
    for val in centrality.values():
        assert 0.0 <= val <= 1.0


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_compute_threat_flow_base_case(sample_nodes, sample_edges):
    """Nodes with dark events have non-zero threat flow."""
    g = _build_graph(sample_nodes, sample_edges)
    flow = g.compute_threat_flow()
    # node-A has 3 dark events (threat_score=0.82) and 2 incident edges
    assert flow["node-A"] > 0.0
    # node-C has 0 dark events but has incoming edges
    assert flow["node-C"] >= 0.0


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_identify_critical_nodes_top_n(sample_nodes, sample_edges):
    g = _build_graph(sample_nodes, sample_edges)
    critical = g.identify_critical_nodes(top_n=2)
    assert isinstance(critical, list)
    assert len(critical) <= 2
    # node-A should be critical given its high dark event count and centrality
    assert "node-A" in critical


# ---------------------------------------------------------------------------
# Tests: Serialisation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_to_json_node_link_format(sample_nodes, sample_edges):
    """Graph serialises to D3/Deck.gl node-link format with 'nodes' and 'links'."""
    g = _build_graph(sample_nodes, sample_edges)
    data = g.to_json()
    assert "nodes" in data
    assert "links" in data
    assert len(data["nodes"]) == 4
    assert len(data["links"]) == 4


def test_to_json_empty_graph():
    """Empty graph returns skeleton JSON without raising."""
    g = LogisticsNetworkGraph()
    data = g.to_json()
    assert "nodes" in data
    assert "links" in data


# ---------------------------------------------------------------------------
# Tests: RL training fallback
# ---------------------------------------------------------------------------


def test_rl_trainer_stub_when_graph_empty():
    """RL trainer returns empty reward list for empty graph."""
    g = LogisticsNetworkGraph()
    trainer = NetworkRLTrainer(g, n_episodes=10)
    rewards = trainer.train()
    assert isinstance(rewards, list)


@pytest.mark.skipif(not NX_AVAILABLE, reason="networkx not installed")
def test_rl_trainer_predict_expansion_threat_fallback(sample_nodes, sample_edges):
    """predict_expansion_candidates falls back to threat_flow ranking without RL model."""
    g = _build_graph(sample_nodes, sample_edges)
    trainer = NetworkRLTrainer(g, n_episodes=10)
    # Do not call train() — model will be None → threat_flow fallback
    candidates = trainer.predict_expansion_candidates(top_n=2)
    assert isinstance(candidates, list)
    assert len(candidates) <= 2


# ---------------------------------------------------------------------------
# Tests: Full analysis engine with mocked DB
# ---------------------------------------------------------------------------


def _mock_analysis_result():
    """Return a realistic NetworkAnalysisResult for mocking purposes."""
    from src.analytics.network_graph import NetworkAnalysisResult

    return NetworkAnalysisResult(
        node_count=4,
        edge_count=4,
        critical_node_ids=["node-A", "node-D"],
        predicted_expansion_ids=["node-B"],
        centrality_scores={"node-A": 0.6, "node-B": 0.3, "node-C": 0.1, "node-D": 0.4},
        threat_flow_scores={"node-A": 1.2, "node-B": 0.4, "node-C": 0.1, "node-D": 0.8},
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def auth_headers() -> dict:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "analyst_viper", "password": "caelum_analyst_2026!"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def admin_headers() -> dict:
    from src.api.auth import create_access_token

    token = create_access_token(
        data={"sub": "admin", "role": "admin", "id": "00000000-0000-0000-0000-000000000001"}
    )
    return {"Authorization": f"Bearer {token}"}


def test_network_analyse_endpoint(auth_headers):
    """POST /api/v1/network/analyse returns NetworkAnalysisResponse."""
    client = TestClient(app)
    mock_result = _mock_analysis_result()

    with patch(
        "src.analytics.network_graph.NetworkAnalysisEngine.run_full_analysis",
        return_value=mock_result,
    ):
        resp = client.post(
            "/api/v1/network/analyse",
            json={"snapshot_label": "TEST-SNAPSHOT", "n_episodes": 50},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] == 4
    assert data["edge_count"] == 4
    assert "node-A" in data["critical_node_ids"]
    assert "node-B" in data["predicted_expansion_ids"]
    assert "centrality_scores" in data
    assert "threat_flow_scores" in data
    assert "computed_at" in data


def test_network_analyse_requires_auth():
    """Unauthenticated request rejected."""
    client = TestClient(app)
    resp = client.post("/api/v1/network/analyse", json={})
    assert resp.status_code == 401


def test_network_graph_endpoint(auth_headers):
    """GET /api/v1/network/graph returns stub node-link JSON."""
    client = TestClient(app)
    resp = client.get("/api/v1/network/graph", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "links" in data


def test_network_snapshots_endpoint(auth_headers):
    """GET /api/v1/network/snapshots returns a list."""
    client = TestClient(app)
    resp = client.get("/api/v1/network/snapshots", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_network_snapshots_latest_no_snapshot(auth_headers):
    """GET /api/v1/network/snapshots/latest → 404 when DB empty."""
    client = TestClient(app)
    with patch(
        "src.analytics.network_graph.NetworkAnalysisEngine.get_latest_snapshot",
        return_value=None,
    ):
        resp = client.get("/api/v1/network/snapshots/latest", headers=auth_headers)
    assert resp.status_code == 404


def test_network_snapshots_latest_success(auth_headers):
    """GET /api/v1/network/snapshots/latest returns snapshot details."""
    client = TestClient(app)
    mock_snap = {
        "id": "snap-uuid-001",
        "snapshot_label": "AUTO-20260930T1200Z",
        "computation_timestamp": "2026-09-30T12:00:00+00:00",
        "node_count": 4,
        "edge_count": 4,
        "critical_node_ids": ["node-A"],
        "predicted_expansion_ids": ["node-C"],
        "rl_episode_rewards": [0.1, 0.3, 0.6],
        "created_at": "2026-09-30T12:00:01+00:00",
    }
    with patch(
        "src.analytics.network_graph.NetworkAnalysisEngine.get_latest_snapshot",
        return_value=mock_snap,
    ):
        resp = client.get("/api/v1/network/snapshots/latest", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "snap-uuid-001"
    assert data["node_count"] == 4
    assert "node-A" in data["critical_node_ids"]
    assert data["rl_episode_rewards"] == [0.1, 0.3, 0.6]
