"""Tactical Edge Delta Protocol & Binary Geometry Compression.

Enables low-bandwidth tactical mesh synchronization for forward appliances (NVIDIA Jetson AGX Orin).
Achieves < 1.5 KB payload per target detection through:
1. Coordinate quantization (fixed-point integer 1e5 for sub-meter resolution).
2. Delta-encoding of polygon vertex offsets (dx, dy).
3. Compact binary packing (target_id UUID, 1-byte class, 1-byte confidence, 1-byte priority).
4. HMAC-SHA256 tamper-proof message authentication.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
Version Two Specification
"""

import hashlib
import hmac
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

CLASS_ENUM_MAP = {
    "LOGISTICS_DEPOT": 0,
    "RUNWAY_TAXIWAY": 1,
    "RADAR_DOME": 2,
    "DEFENSE_REVETMENT": 3,
    "INDUSTRIAL_BUILDING": 4,
    "UNKNOWN_STRUCTURE": 5,
}

REVERSE_CLASS_MAP = {v: k for k, v in CLASS_ENUM_MAP.items()}


@dataclass
class TacticalDelta:
    """Decoded target delta payload."""

    target_id: str
    classification: str
    confidence: float
    priority_score: float
    coordinates: List[Tuple[float, float]]  # [(lon, lat), ...]
    timestamp: float
    hmac_valid: bool = True


class DeltaProtocolEncoder:
    """Encodes and decodes tactical polygon deltas with HMAC integrity."""

    def __init__(self, shared_secret: str = "caelum_tactical_mesh_key_2026"):
        self.secret_bytes = shared_secret.encode("utf-8")

    def encode_delta(
        self,
        target_id: str,
        classification: str,
        confidence: float,
        priority_score: float,
        coordinates: List[Tuple[float, float]],
        timestamp: Optional[float] = None,
    ) -> bytes:
        """Compress target detection into compact signed binary payload (< 1.5 KB).

        Layout:
        - 16 bytes: Target UUID
        - 1 byte: Classification Enum (0-5)
        - 1 byte: Confidence (0-255 -> 0.0-1.0)
        - 1 byte: Priority Score (0-100)
        - 4 bytes: Unix Timestamp (uint32)
        - 2 bytes: Number of vertices (uint16)
        - Variable: Base vertex (2x int32) + Delta offsets (2x int16 per vertex)
        - 16 bytes: HMAC-SHA256 signature prefix
        """
        raw_uuid = uuid.UUID(target_id).bytes
        class_byte = CLASS_ENUM_MAP.get(classification, 5)
        conf_byte = int(round(np_clip(confidence, 0.0, 1.0) * 255))
        prio_byte = int(round(np_clip(priority_score, 0.0, 100.0)))
        ts = int(timestamp or datetime.now(timezone.utc).timestamp())
        n_vertices = len(coordinates)

        header = struct.pack(
            ">16sBBBIH", raw_uuid, class_byte, conf_byte, prio_byte, ts, n_vertices
        )

        coords_bytes = bytearray()
        if n_vertices > 0:
            # Anchor first vertex at 1e5 fixed point
            base_x = int(coordinates[0][0] * 100000)
            base_y = int(coordinates[0][1] * 100000)
            coords_bytes.extend(struct.pack(">ii", base_x, base_y))

            prev_x, prev_y = base_x, base_y
            for lon, lat in coordinates[1:]:
                curr_x = int(lon * 100000)
                curr_y = int(lat * 100000)
                dx = max(-32768, min(32767, curr_x - prev_x))
                dy = max(-32768, min(32767, curr_y - prev_y))
                coords_bytes.extend(struct.pack(">hh", dx, dy))
                prev_x, prev_y = curr_x, curr_y

        body = header + bytes(coords_bytes)
        signature = hmac.new(self.secret_bytes, body, hashlib.sha256).digest()[:16]

        packed = body + signature
        return packed

    def decode_delta(self, payload: bytes) -> TacticalDelta:
        """Decode and verify binary tactical delta."""
        if len(payload) < 25 + 16:
            raise ValueError(f"Payload too short for tactical delta: {len(payload)} bytes")

        body = payload[:-16]
        expected_sig = payload[-16:]
        calculated_sig = hmac.new(self.secret_bytes, body, hashlib.sha256).digest()[:16]
        hmac_valid = hmac.compare_digest(expected_sig, calculated_sig)

        raw_uuid, class_byte, conf_byte, prio_byte, ts, n_vertices = struct.unpack(
            ">16sBBBIH", body[:25]
        )
        target_id = str(uuid.UUID(bytes=raw_uuid))
        classification = REVERSE_CLASS_MAP.get(class_byte, "UNKNOWN_STRUCTURE")
        confidence = round(conf_byte / 255.0, 3)
        priority_score = float(prio_byte)

        coords: List[Tuple[float, float]] = []
        offset = 25
        if n_vertices > 0 and len(body) >= offset + 8:
            base_x, base_y = struct.unpack(">ii", body[offset : offset + 8])
            coords.append((round(base_x / 100000.0, 5), round(base_y / 100000.0, 5)))
            offset += 8

            curr_x, curr_y = base_x, base_y
            for _ in range(n_vertices - 1):
                if offset + 4 > len(body):
                    break
                dx, dy = struct.unpack(">hh", body[offset : offset + 4])
                curr_x += dx
                curr_y += dy
                coords.append((round(curr_x / 100000.0, 5), round(curr_y / 100000.0, 5)))
                offset += 4

        return TacticalDelta(
            target_id=target_id,
            classification=classification,
            confidence=confidence,
            priority_score=priority_score,
            coordinates=coords,
            timestamp=float(ts),
            hmac_valid=hmac_valid,
        )


def np_clip(val: float, low: float, high: float) -> float:
    """Helper to clip float value within bounds."""
    return max(low, min(high, val))
