"""Tactical Edge Synchronization Manager.

Orchestrates store-and-forward delta synchronization between forward tactical edge
appliances (e.g., Jetson AGX Orin) and central HQ Citus PostGIS cluster over
low-bandwidth SATCOM, UHF, or ad-hoc tactical radio meshes.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
Version Two Specification
"""

import base64
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import structlog

from src.edge.delta_protocol import DeltaProtocolEncoder, TacticalDelta

logger = structlog.get_logger(__name__)


@dataclass
class TacticalSyncStatus:
    """Status report of the forward edge mesh synchronizer."""

    node_id: str
    connected: bool
    pending_deltas_count: int
    total_synced_count: int
    last_sync_timestamp: Optional[float]
    bandwidth_bytes_sent: int
    bandwidth_bytes_received: int


class EdgeSyncManager:
    """Manages queueing, serialization, and synchronization of tactical deltas."""

    def __init__(self, node_id: str = "tactical_edge_node_01", secret_key: Optional[str] = None):
        self.node_id = node_id
        self.encoder = DeltaProtocolEncoder(
            shared_secret=secret_key or "caelum_tactical_mesh_key_2026"
        )
        self._outgoing_queue: List[bytes] = []
        self._synced_history: List[TacticalDelta] = []
        self._bytes_sent = 0
        self._bytes_received = 0
        self._last_sync: Optional[float] = None
        self._is_connected = True

    def queue_detection_delta(
        self,
        target_id: str,
        classification: str,
        confidence: float,
        priority_score: float,
        coordinates: List[Tuple[float, float]],
    ) -> bytes:
        """Encode detection into compressed binary delta and queue for transmission."""
        payload = self.encoder.encode_delta(
            target_id=target_id,
            classification=classification,
            confidence=confidence,
            priority_score=priority_score,
            coordinates=coordinates,
        )
        self._outgoing_queue.append(payload)
        logger.debug(
            "Queued tactical delta for transmission",
            target_id=target_id,
            bytes_size=len(payload),
            queue_length=len(self._outgoing_queue),
        )
        return payload

    def prepare_sync_batch(self, max_batch_size: int = 50) -> Dict[str, Any]:
        """Package queued deltas into a base64-encoded sync bundle."""
        batch = self._outgoing_queue[:max_batch_size]
        encoded_items = [base64.b64encode(item).decode("utf-8") for item in batch]
        payload_bytes = sum(len(item) for item in batch)

        return {
            "node_id": self.node_id,
            "timestamp": time.time(),
            "batch_size": len(batch),
            "payload_bytes": payload_bytes,
            "deltas_b64": encoded_items,
        }

    def acknowledge_sync_batch(self, count: int) -> None:
        """Acknowledge successful transmission from central HQ."""
        sent = self._outgoing_queue[:count]
        self._bytes_sent += sum(len(b) for b in sent)
        self._outgoing_queue = self._outgoing_queue[count:]
        self._last_sync = time.time()

    def receive_and_apply_batch(self, sync_bundle: Dict[str, Any]) -> List[TacticalDelta]:
        """Central HQ processing of incoming edge sync batch."""
        raw_items = sync_bundle.get("deltas_b64", [])
        decoded_deltas: List[TacticalDelta] = []

        for b64 in raw_items:
            raw_bytes = base64.b64decode(b64)
            self._bytes_received += len(raw_bytes)
            try:
                delta = self.encoder.decode_delta(raw_bytes)
                if delta.hmac_valid:
                    decoded_deltas.append(delta)
                    self._synced_history.append(delta)
                else:
                    logger.warning(
                        "Rejected delta with invalid HMAC signature", target_id=delta.target_id
                    )
            except Exception as exc:
                logger.error("Failed to decode incoming tactical delta", error=str(exc))

        self._last_sync = time.time()
        logger.info(
            "Applied tactical edge sync batch",
            node_id=sync_bundle.get("node_id"),
            accepted_count=len(decoded_deltas),
        )
        return decoded_deltas

    def get_status(self) -> TacticalSyncStatus:
        """Return real-time edge sync telemetry."""
        return TacticalSyncStatus(
            node_id=self.node_id,
            connected=self._is_connected,
            pending_deltas_count=len(self._outgoing_queue),
            total_synced_count=len(self._synced_history),
            last_sync_timestamp=self._last_sync,
            bandwidth_bytes_sent=self._bytes_sent,
            bandwidth_bytes_received=self._bytes_received,
        )


# Global instance
edge_sync = EdgeSyncManager()
