"""Logistics Network Graph Engine for Project Caelum-EO — Version 5.

Constructs a directed graph of infrastructure detections (nodes) and telemetry
flow paths (edges) using NetworkX. Trains a Reinforcement Learning agent
(Stable Baselines3 / Gymnasium) to identify supply-chain critical points and
predict future infrastructure build-out locations.

Air-gapped, fully local. No external API calls.
Repository: github.com/FranekJemiolo/Caelum-EO
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psycopg2
import structlog
from psycopg2.extras import RealDictCursor

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports with graceful fallback
# ---------------------------------------------------------------------------
try:
    import networkx as nx
    from networkx.readwrite import json_graph as nx_json

    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False
    logger.warning("networkx not available — graph engine operating in stub mode")

try:
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3 import PPO

    _RL_AVAILABLE = True
except ImportError:
    _RL_AVAILABLE = False
    logger.warning("gymnasium/stable-baselines3 not available — RL training stub mode")

# ---------------------------------------------------------------------------
# Database config (mirrors telemetry_ingest.py)
# ---------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "caelum_geoint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "caelum_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "caelum_secure_password")

MODEL_CHECKPOINT_DIR = Path(os.getenv("CAELUM_MODEL_DIR", "./weights/rl_network"))
RL_DEFAULT_EPISODES = int(os.getenv("RL_TRAINING_EPISODES", "500"))


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------
@dataclass
class InfraNode:
    """Graph node representing a detected infrastructure target."""

    node_id: str  # detection UUID
    classification: str
    lon: float
    lat: float
    priority_score: float
    area_sq_m: float
    zone_id: Optional[str] = None
    dark_event_count: int = 0  # Number of correlated dark events
    threat_score: float = 0.0  # Aggregated from dark events


@dataclass
class TelemetryEdge:
    """Graph edge representing a telemetry flow path between two nodes."""

    source_id: str
    target_id: str
    entity_type: str  # "AIS" | "ADSB"
    flow_count: int  # Number of unique tracks using this path
    mean_dark_threat: float  # Mean threat score of dark events on this edge
    distance_km: float


@dataclass
class NetworkAnalysisResult:
    """Result of network critical-point and expansion analysis."""

    node_count: int
    edge_count: int
    critical_node_ids: List[str]  # High-betweenness-centrality nodes
    predicted_expansion_ids: List[str]  # RL-predicted next build-out candidates
    centrality_scores: Dict[str, float]
    threat_flow_scores: Dict[str, float]
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


class LogisticsNetworkGraph:
    """Builds and analyses the logistics network graph from PostGIS data.

    Nodes: infrastructure_detections (with aggregated dark event counts).
    Edges: Telemetry flows — two nodes are connected if a vessel/aircraft
           went dark near both within the configured time window.
    """

    def __init__(self, db_conn: Optional[psycopg2.extensions.connection] = None) -> None:
        self._external_conn = db_conn
        self._graph: Any = None  # nx.DiGraph or None

    def _get_conn(self) -> psycopg2.extensions.connection:
        if self._external_conn is not None:
            return self._external_conn
        return psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )

    def _load_nodes(self, conn: psycopg2.extensions.connection) -> List[InfraNode]:
        """Load infrastructure detections as graph nodes, enriched with dark event counts."""
        nodes: List[InfraNode] = []
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        d.id::text AS node_id,
                        d.classification,
                        ST_X(d.centroid) AS lon,
                        ST_Y(d.centroid) AS lat,
                        COALESCE(d.priority_score, 0.5) AS priority_score,
                        COALESCE(d.area_sq_meters, 0.0) AS area_sq_m,
                        d.zone_id::text AS zone_id,
                        COUNT(de.id) AS dark_event_count,
                        COALESCE(AVG(de.threat_score), 0.0) AS threat_score
                    FROM infrastructure_detections d
                    LEFT JOIN dark_target_events de ON de.detection_id = d.id
                    GROUP BY d.id, d.classification, d.centroid, d.priority_score,
                             d.area_sq_meters, d.zone_id
                    ORDER BY d.priority_score DESC
                    """
                )
                for row in cur.fetchall():
                    nodes.append(
                        InfraNode(
                            node_id=row["node_id"],
                            classification=row["classification"],
                            lon=float(row["lon"]),
                            lat=float(row["lat"]),
                            priority_score=float(row["priority_score"]),
                            area_sq_m=float(row["area_sq_m"]),
                            zone_id=row["zone_id"],
                            dark_event_count=int(row["dark_event_count"]),
                            threat_score=float(row["threat_score"]),
                        )
                    )
        except Exception as exc:
            logger.warning("Node load failed — using empty graph", error=str(exc))
        return nodes

    def _load_edges(self, conn: psycopg2.extensions.connection) -> List[TelemetryEdge]:
        """Load dark-event flows as directed edges between node pairs.

        Two detection nodes are linked if the same entity (MMSI/ICAO24) triggered
        dark events near both, within a 72-hour window. Edge weight = flow count
        and mean threat score.
        """
        edges: List[TelemetryEdge] = []
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Self-join dark_target_events by entity within time window
                cur.execute(
                    """
                    SELECT
                        e1.detection_id::text  AS source_id,
                        e2.detection_id::text  AS target_id,
                        e1.event_type,
                        COUNT(*)               AS flow_count,
                        AVG((e1.threat_score + e2.threat_score) / 2) AS mean_dark_threat,
                        AVG(
                            ST_Distance(d1.centroid::geography, d2.centroid::geography) / 1000.0
                        ) AS distance_km
                    FROM dark_target_events e1
                    JOIN dark_target_events e2
                        ON  e1.entity_id  = e2.entity_id
                        AND e1.event_type = e2.event_type
                        AND e1.detection_id <> e2.detection_id
                        AND ABS(EXTRACT(EPOCH FROM (e1.dark_start - e2.dark_start))) < 259200
                    JOIN infrastructure_detections d1 ON d1.id = e1.detection_id
                    JOIN infrastructure_detections d2 ON d2.id = e2.detection_id
                    GROUP BY e1.detection_id, e2.detection_id, e1.event_type
                    HAVING COUNT(*) >= 1
                    ORDER BY flow_count DESC
                    LIMIT 2000
                    """
                )
                for row in cur.fetchall():
                    edges.append(
                        TelemetryEdge(
                            source_id=row["source_id"],
                            target_id=row["target_id"],
                            entity_type=row["event_type"],
                            flow_count=int(row["flow_count"]),
                            mean_dark_threat=float(row["mean_dark_threat"]),
                            distance_km=float(row["distance_km"]),
                        )
                    )
        except Exception as exc:
            logger.warning("Edge load failed — using edgeless graph", error=str(exc))
        return edges

    def build(
        self, conn: Optional[psycopg2.extensions.connection] = None
    ) -> "LogisticsNetworkGraph":
        """Build the logistics network DiGraph from PostGIS data."""
        if not _NX_AVAILABLE:
            logger.warning("networkx unavailable — skipping graph build")
            return self

        db = conn or self._get_conn()
        nodes = self._load_nodes(db)
        edges = self._load_edges(db)

        g = nx.DiGraph()
        for node in nodes:
            g.add_node(
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
            if g.has_node(edge.source_id) and g.has_node(edge.target_id):
                g.add_edge(
                    edge.source_id,
                    edge.target_id,
                    entity_type=edge.entity_type,
                    flow_count=edge.flow_count,
                    mean_dark_threat=edge.mean_dark_threat,
                    distance_km=edge.distance_km,
                    weight=edge.mean_dark_threat * edge.flow_count,
                )

        self._graph = g
        logger.info(
            "Logistics network graph built",
            nodes=g.number_of_nodes(),
            edges=g.number_of_edges(),
        )
        return self

    @property
    def graph(self) -> Any:
        """Access the underlying NetworkX DiGraph."""
        return self._graph

    def compute_centrality(self) -> Dict[str, float]:
        """Compute betweenness centrality for all nodes.

        High-centrality nodes are critical supply chain chokepoints.
        Returns node_id → centrality score mapping.
        """
        if not _NX_AVAILABLE or self._graph is None:
            return {}
        try:
            return nx.betweenness_centrality(self._graph, weight="weight", normalized=True)
        except Exception as exc:
            logger.warning("Centrality computation failed", error=str(exc))
            return {}

    def compute_threat_flow(self) -> Dict[str, float]:
        """Compute aggregated threat flow score for each node.

        Score = node threat_score + sum of incident edge mean_dark_threat × flow_count.
        """
        if not _NX_AVAILABLE or self._graph is None:
            return {}
        scores: Dict[str, float] = {}
        for node_id, data in self._graph.nodes(data=True):
            base = float(data.get("threat_score", 0.0))
            flow_in = sum(
                edata.get("mean_dark_threat", 0.0) * edata.get("flow_count", 1)
                for _, _, edata in self._graph.in_edges(node_id, data=True)
            )
            flow_out = sum(
                edata.get("mean_dark_threat", 0.0) * edata.get("flow_count", 1)
                for _, _, edata in self._graph.out_edges(node_id, data=True)
            )
            scores[node_id] = round(base + flow_in + flow_out, 4)
        return scores

    def identify_critical_nodes(self, top_n: int = 10) -> List[str]:
        """Return top-N most critical nodes by combined centrality + threat flow."""
        centrality = self.compute_centrality()
        threat_flow = self.compute_threat_flow()
        all_nodes = set(centrality.keys()) | set(threat_flow.keys())
        combined = {nid: centrality.get(nid, 0.0) + threat_flow.get(nid, 0.0) for nid in all_nodes}
        return sorted(combined, key=combined.get, reverse=True)[:top_n]  # type: ignore[arg-type]

    def to_json(self) -> Dict[str, Any]:
        """Serialise graph to node-link JSON (compatible with D3 / Deck.gl)."""
        if not _NX_AVAILABLE or self._graph is None:
            return {"nodes": [], "links": [], "edges": []}
        try:
            data = nx_json.node_link_data(self._graph, edges="links")
        except TypeError:
            data = nx_json.node_link_data(self._graph)
        # Ensure both 'links' and 'edges' are present for broad compatibility
        if "links" in data and "edges" not in data:
            data["edges"] = data["links"]
        elif "edges" in data and "links" not in data:
            data["links"] = data["edges"]
        return data

    def save_snapshot(self, conn: psycopg2.extensions.connection, label: str) -> str:
        """Persist current graph as a network_snapshots row. Returns snapshot UUID."""
        critical_ids = self.identify_critical_nodes(top_n=10)
        graph_json = self.to_json()
        g = self._graph
        node_count = g.number_of_nodes() if g else 0
        edge_count = g.number_of_edges() if g else 0

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO network_snapshots
                    (snapshot_label, node_count, edge_count, critical_node_ids, graph_json)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id::text
                """,
                (label, node_count, edge_count, critical_ids, json.dumps(graph_json)),
            )
            row = cur.fetchone()
        conn.commit()
        snapshot_id = row[0] if row else ""
        logger.info("Network snapshot saved", snapshot_id=snapshot_id, label=label)
        return snapshot_id


# ---------------------------------------------------------------------------
# Gymnasium RL Environment
# ---------------------------------------------------------------------------

if _RL_AVAILABLE and _NX_AVAILABLE:

    class LogisticsNetworkEnv(gym.Env):
        """Gymnasium environment for RL-based logistics network vulnerability analysis.

        The agent traverses the infrastructure graph step-by-step, selecting nodes
        to "investigate". Reward is proportional to the combined centrality + threat
        flow score of the chosen node. The agent learns which nodes represent the
        highest-value targets for intelligence tasking.

        Observation space: Feature vector for current node:
            [priority_score, threat_score, dark_event_count (normalised),
             degree_centrality, threat_flow_score]
        Action space: Discrete — select any node in the graph by index.
        """

        metadata: Dict[str, Any] = {"render_modes": []}

        def __init__(self, network: LogisticsNetworkGraph) -> None:
            super().__init__()
            self._network = network
            self._g = network.graph
            self._node_ids: List[str] = list(self._g.nodes()) if self._g is not None else []
            n = max(len(self._node_ids), 1)

            self.action_space = spaces.Discrete(n)
            # [priority_score, threat_score, norm_dark_count, degree_centrality, threat_flow]
            self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(5,), dtype=np.float32)
            self._centrality: Dict[str, float] = {}
            self._threat_flow: Dict[str, float] = {}
            self._visited: set = set()
            self._current_node_idx: int = 0
            self._max_steps = min(n * 2, 200)
            self._step_count = 0

        def _precompute_scores(self) -> None:
            self._centrality = self._network.compute_centrality()
            self._threat_flow = self._network.compute_threat_flow()
            max_dark = max(
                (self._g.nodes[nid].get("dark_event_count", 0) for nid in self._node_ids),
                default=1,
            )
            self._max_dark_count = max(max_dark, 1)

        def _obs_for_node(self, node_id: str) -> np.ndarray:
            data = self._g.nodes.get(node_id, {})
            priority = float(data.get("priority_score", 0.0))
            threat = float(data.get("threat_score", 0.0))
            dark_count = float(data.get("dark_event_count", 0)) / self._max_dark_count
            centrality = float(self._centrality.get(node_id, 0.0))
            flow = min(float(self._threat_flow.get(node_id, 0.0)), 1.0)
            return np.array([priority, threat, dark_count, centrality, flow], dtype=np.float32)

        def reset(
            self,
            *,
            seed: Optional[int] = None,
            options: Optional[Dict[str, Any]] = None,
        ) -> Tuple[np.ndarray, Dict[str, Any]]:
            super().reset(seed=seed)
            self._precompute_scores()
            self._visited = set()
            self._step_count = 0
            if self._node_ids:
                self._current_node_idx = int(self.np_random.integers(0, len(self._node_ids)))
            obs = (
                self._obs_for_node(self._node_ids[self._current_node_idx])
                if self._node_ids
                else np.zeros(5, dtype=np.float32)
            )
            return obs, {}

        def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
            self._step_count += 1
            action = int(action) % len(self._node_ids) if self._node_ids else 0
            node_id = self._node_ids[action] if self._node_ids else ""

            # Reward: combined centrality + threat flow, penalise revisits
            if node_id in self._visited:
                reward = -0.1
            else:
                c = self._centrality.get(node_id, 0.0)
                t = self._threat_flow.get(node_id, 0.0)
                reward = float(c + min(t, 1.0))
                self._visited.add(node_id)

            self._current_node_idx = action
            terminated = self._step_count >= self._max_steps
            obs = self._obs_for_node(node_id) if node_id else np.zeros(5, dtype=np.float32)
            return obs, reward, terminated, False, {"node_id": node_id}

        def render(self) -> None:
            pass


# ---------------------------------------------------------------------------
# RL Training Interface
# ---------------------------------------------------------------------------


class NetworkRLTrainer:
    """Trains an RL agent on the logistics network graph and predicts expansions.

    Uses Stable Baselines3 PPO with a simple MLP policy. Model checkpoints
    are saved to the local weights directory (air-gapped, no cloud sync).
    """

    def __init__(
        self,
        network: LogisticsNetworkGraph,
        checkpoint_dir: Path = MODEL_CHECKPOINT_DIR,
        n_episodes: int = RL_DEFAULT_EPISODES,
    ) -> None:
        self._network = network
        self._checkpoint_dir = checkpoint_dir
        self._n_episodes = n_episodes
        self._model: Any = None
        self._episode_rewards: List[float] = []

    def train(self) -> List[float]:
        """Train the PPO agent and return episode reward history."""
        if not _RL_AVAILABLE:
            logger.warning("RL libraries unavailable — returning stub rewards")
            self._episode_rewards = [float(i) * 0.01 for i in range(self._n_episodes)]
            return self._episode_rewards

        if self._network.graph is None or self._network.graph.number_of_nodes() == 0:
            logger.warning("Empty graph — skipping RL training")
            self._episode_rewards = []
            return []

        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        env = LogisticsNetworkEnv(self._network)
        self._model = PPO("MlpPolicy", env, verbose=0, n_steps=64, batch_size=32)

        # Calculate total timesteps from desired episodes × max_steps
        total_timesteps = self._n_episodes * env._max_steps
        self._model.learn(total_timesteps=total_timesteps)

        # Save checkpoint
        checkpoint_path = self._checkpoint_dir / "network_agent"
        self._model.save(str(checkpoint_path))
        logger.info("RL model saved", checkpoint=str(checkpoint_path))

        # Collect rewards by running evaluation episodes
        rewards: List[float] = []
        obs, _ = env.reset()
        episode_reward = 0.0
        for _ in range(min(self._n_episodes, 200)):
            action, _ = self._model.predict(obs, deterministic=True)
            obs, reward, terminated, _, _ = env.step(int(action))
            episode_reward += float(reward)
            if terminated:
                rewards.append(episode_reward)
                episode_reward = 0.0
                obs, _ = env.reset()
        self._episode_rewards = rewards
        return rewards

    def predict_expansion_candidates(self, top_n: int = 5) -> List[str]:
        """Use the trained agent to identify top-N next expansion locations.

        Runs the agent greedily across all nodes and selects the highest-value
        unvisited nodes as predicted build-out candidates.
        """
        if not _RL_AVAILABLE or self._model is None:
            # Fallback: use raw threat flow ranking
            threat_flow = self._network.compute_threat_flow()
            return sorted(threat_flow, key=threat_flow.get, reverse=True)[:top_n]  # type: ignore[arg-type]

        if self._network.graph is None:
            return []

        env = LogisticsNetworkEnv(self._network)
        obs, _ = env.reset()
        scores: Dict[str, float] = {}
        for _ in range(min(len(env._node_ids), 100)):
            action, _ = self._model.predict(obs, deterministic=True)
            obs, reward, terminated, _, info = env.step(int(action))
            node_id = info.get("node_id", "")
            if node_id and node_id not in scores:
                scores[node_id] = float(reward)
            if terminated:
                break

        return sorted(scores, key=scores.get, reverse=True)[:top_n]  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


class NetworkAnalysisEngine:
    """High-level orchestrator: build graph → analyse → train RL → save snapshot."""

    def __init__(self, db_conn: Optional[psycopg2.extensions.connection] = None) -> None:
        self._db_conn = db_conn
        self._network = LogisticsNetworkGraph(db_conn)
        self._trainer: Optional[NetworkRLTrainer] = None

    def _get_conn(self) -> psycopg2.extensions.connection:
        if self._db_conn is not None:
            return self._db_conn
        return psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )

    def run_full_analysis(
        self,
        snapshot_label: Optional[str] = None,
        n_episodes: int = RL_DEFAULT_EPISODES,
    ) -> NetworkAnalysisResult:
        """Full pipeline: build → analyse → train RL → persist snapshot."""
        conn = self._get_conn()
        self._network.build(conn)

        centrality = self._network.compute_centrality()
        threat_flow = self._network.compute_threat_flow()
        critical_ids = self._network.identify_critical_nodes(top_n=10)

        # RL training
        self._trainer = NetworkRLTrainer(self._network, n_episodes=n_episodes)
        rewards = self._trainer.train()
        expansion_ids = self._trainer.predict_expansion_candidates(top_n=5)

        g = self._network.graph
        node_count = g.number_of_nodes() if g is not None else 0
        edge_count = g.number_of_edges() if g is not None else 0

        # Persist snapshot
        label = snapshot_label or f"AUTO-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')}"
        try:
            snapshot_id = self._network.save_snapshot(conn, label)
            # Update RL rewards and predicted expansion in snapshot row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE network_snapshots
                    SET rl_episode_rewards = %s,
                        predicted_expansion_ids = %s,
                        rl_model_path = %s
                    WHERE id::text = %s
                    """,
                    (
                        rewards,
                        expansion_ids,
                        str(MODEL_CHECKPOINT_DIR / "network_agent"),
                        snapshot_id,
                    ),
                )
            conn.commit()
        except Exception as exc:
            logger.warning("Snapshot save failed", error=str(exc))

        result = NetworkAnalysisResult(
            node_count=node_count,
            edge_count=edge_count,
            critical_node_ids=critical_ids,
            predicted_expansion_ids=expansion_ids,
            centrality_scores=centrality,
            threat_flow_scores=threat_flow,
        )
        logger.info(
            "Network analysis complete",
            nodes=node_count,
            edges=edge_count,
            critical=len(critical_ids),
            expansions=len(expansion_ids),
            rl_episodes=len(rewards),
        )
        return result

    def get_graph_json(self) -> Dict[str, Any]:
        """Return current graph as serialisable node-link JSON."""
        return self._network.to_json()

    def get_latest_snapshot(
        self, conn: Optional[psycopg2.extensions.connection] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent network snapshot from the database."""
        db = conn or self._get_conn()
        try:
            with db.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id::text, snapshot_label, computation_timestamp,
                           node_count, edge_count, critical_node_ids,
                           predicted_expansion_ids, rl_episode_rewards,
                           graph_json, created_at
                    FROM network_snapshots
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as exc:
            logger.warning("Failed to fetch latest snapshot", error=str(exc))
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
network_engine = NetworkAnalysisEngine()
