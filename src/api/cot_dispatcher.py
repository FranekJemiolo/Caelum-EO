"""Tactical Edge Cursor-on-Target (CoT) XML Dispatcher for ATAK Integration.

Serializes PostGIS verified satellite detections into standard Cursor-on-Target (CoT)
XML event messages mapped to MIL-STD-2525 symbol codes, broadcasting them over UDP/TCP
to tactical edge Android Team Awareness Kit (ATAK) clients and TAK Servers.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import json
import os
import socket
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import click
import structlog

logger = structlog.get_logger(__name__)

# Tactical TAK Server Network Defaults
DEFAULT_TAK_HOST = os.getenv("TAK_SERVER_HOST", "127.0.0.1")
DEFAULT_TAK_PORT = int(os.getenv("TAK_SERVER_PORT", "8087"))
DEFAULT_TAK_PROTO = os.getenv("TAK_PROTO", "udp").lower()

# MIL-STD-2525C/D 2525 Symbol Code Mapping for Ground Installations & Equipment
# Prefix 'a-h-G' indicates Hostile Ground (standard GEOINT threat designation)
MIL_STD_2525_CODES: Dict[str, str] = {
    "RADAR_DOME": "a-h-G-U-C-R",  # Ground Equipment - Sensor / Radar Installation
    "SAM_SITE": "a-h-G-U-C-M",  # Ground Equipment - Surface-to-Air Missile (SAM)
    "RUNWAY_TAXIWAY": "a-f-G-I-A",  # Ground Installation - Aviation / Airfield Runway
    "LOGISTICS_DEPOT": "a-h-G-I-S",  # Ground Installation - Supply / Logistics Depot
    "DEFENSE_REVETMENT": "a-h-G-I-M",  # Ground Installation - Military Berm / Revetment
    "INDUSTRIAL_BUILDING": "a-h-G-I-B",  # Ground Installation - Production / Industrial
}
DEFAULT_MIL_STD_CODE = "a-h-G-I"  # Generic Hostile Ground Installation


class CoTDispatcher:
    """Serializes GEOINT detections to CoT XML and broadcasts to ATAK / TAK Servers."""

    def __init__(
        self,
        tak_host: str = DEFAULT_TAK_HOST,
        tak_port: int = DEFAULT_TAK_PORT,
        tak_proto: str = DEFAULT_TAK_PROTO,
        db_conn: Any = None,
    ):
        self.tak_host = tak_host
        self.tak_port = tak_port
        self.tak_proto = tak_proto
        self._conn = db_conn

    def get_connection(self):
        """Obtain a live PostGIS connection or fallback."""
        if self._conn is not None:
            return self._conn
        try:
            import psycopg2

            self._conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", 5432)),
                dbname=os.getenv("POSTGRES_DB", "caelum_geoint"),
                user=os.getenv("POSTGRES_USER", "caelum_user"),
                password=os.getenv("POSTGRES_PASSWORD", "caelum_secure_password"),
                connect_timeout=3,
            )
            self._conn.autocommit = True
            return self._conn
        except Exception as exc:
            logger.debug(
                "Live PostGIS unavailable for CoT dispatcher; using memory fallback", error=str(exc)
            )
            return None

    @staticmethod
    def extract_coordinates(detection: Dict[str, Any]) -> Tuple[float, float, float]:
        """Extract representative [lon, lat, elevation] from detection structure."""
        lon, lat, ele = 23.23, 54.14, 0.0

        # Check explicit elevation
        if "elevation_msl" in detection and detection["elevation_msl"] is not None:
            ele = float(detection["elevation_msl"])

        # Coordinates tuple/list
        if "coordinates" in detection and isinstance(detection["coordinates"], (list, tuple)):
            coords = detection["coordinates"]
            if len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])
            if len(coords) >= 3:
                ele = float(coords[2])
            return lon, lat, ele

        # GeoJSON geometry parsing
        geom = detection.get("geometry")
        if isinstance(geom, str):
            try:
                geom = json.loads(geom)
            except Exception:
                geom = None

        if isinstance(geom, dict):
            coords = geom.get("coordinates", [])
            geom_type = geom.get("type", "")

            if geom_type == "Point" and len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])
                if len(coords) >= 3:
                    ele = float(coords[2])
            elif geom_type in ("Polygon", "MultiPolygon") and coords:
                # Compute centroid of exterior ring
                ring = coords[0] if geom_type == "Polygon" else coords[0][0]
                if ring:
                    lons = [pt[0] for pt in ring]
                    lats = [pt[1] for pt in ring]
                    lon = sum(lons) / len(lons)
                    lat = sum(lats) / len(lats)
                    if len(ring[0]) >= 3:
                        ele = sum(pt[2] for pt in ring) / len(ring)

        # Explicit elevation_msl takes precedence if provided
        if "elevation_msl" in detection and detection["elevation_msl"] is not None:
            ele = float(detection["elevation_msl"])

        return lon, lat, ele

    @classmethod
    def get_mil_std_code(cls, classification: str) -> str:
        """Map detection infrastructure classification to MIL-STD-2525 symbol code."""
        norm_class = classification.upper().strip()
        return MIL_STD_2525_CODES.get(norm_class, DEFAULT_MIL_STD_CODE)

    def serialize_cot_xml(
        self,
        detection: Dict[str, Any],
        validity_hours: float = 24.0,
    ) -> Tuple[str, str, str, str]:
        """Serialize a detection into standard Cursor-on-Target (CoT) XML payload.

        Returns:
            Tuple of (xml_string, uid, mil_std_code, callsign)
        """
        det_id = str(detection.get("id") or detection.get("detection_id", "00000000"))
        classification = str(
            detection.get("verified_class")
            or detection.get("classification")
            or "UNKNOWN_STRUCTURE"
        ).upper()

        lon, lat, ele = self.extract_coordinates(detection)
        cot_type = self.get_mil_std_code(classification)

        now = datetime.now(timezone.utc)
        stale = now + timedelta(hours=validity_hours)

        now_str = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
        stale_str = stale.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"

        uid = f"caelum-{det_id}"
        callsign = f"CAELUM-{classification.replace('_', '-')}-{det_id[:6]}"

        confidence = float(detection.get("confidence", 0.85)) * 100.0
        area = float(detection.get("area_sq_meters") or detection.get("surface_area_m2") or 0.0)
        zone = str(detection.get("zone_id", "THEATER-SECTOR"))
        notes = str(detection.get("reviewer_notes") or "GEOINT-verified structural build-up")

        remarks = (
            f"[CAELUM-EO GEOINT] Class: {classification} | Conf: {confidence:.1f}% | "
            f"Area: {area:,.0f}m² | Zone: {zone} | Notes: {notes}"
        )

        # Build standard CoT XML schema
        event = ET.Element(
            "event",
            attrib={
                "version": "2.0",
                "uid": uid,
                "type": cot_type,
                "time": now_str,
                "start": now_str,
                "stale": stale_str,
                "how": "m-g",  # Machine-generated GEOINT
            },
        )

        ET.SubElement(
            event,
            "point",
            attrib={
                "lat": f"{lat:.6f}",
                "lon": f"{lon:.6f}",
                "hae": f"{ele:.1f}",  # Height Above Ellipsoid (meters MSL)
                "ce": "10.0",  # Circular Error 90%
                "le": "15.0",  # Linear Error 90%
            },
        )

        detail = ET.SubElement(event, "detail")
        ET.SubElement(detail, "contact", attrib={"callsign": callsign})
        ET.SubElement(detail, "remarks").text = remarks
        ET.SubElement(
            detail,
            "precisionlocation",
            attrib={"altsrc": "Copernicus GLO-30 DEM", "geopointsrc": "Sentinel-2/Prithvi ML"},
        )
        ET.SubElement(
            detail,
            "caelum_metadata",
            attrib={
                "detection_id": det_id,
                "classification": classification,
                "confidence": f"{confidence:.1f}",
                "priority_score": str(detection.get("priority_score", "0.90")),
                "zone_id": zone,
            },
        )

        xml_bytes = ET.tostring(event, encoding="utf-8", xml_declaration=True)
        xml_str = xml_bytes.decode("utf-8")
        return xml_str, uid, cot_type, callsign

    def send_socket_payload(
        self,
        xml_payload: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        proto: Optional[str] = None,
        timeout: float = 2.0,
    ) -> bool:
        """Transmit raw CoT XML payload over UDP or TCP to target TAK server/multicast."""
        target_host = host or self.tak_host
        target_port = port or self.tak_port
        protocol = (proto or self.tak_proto).lower()

        data = xml_payload.encode("utf-8")

        try:
            if protocol == "tcp":
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(timeout)
                    sock.connect((target_host, target_port))
                    sock.sendall(data)
            else:  # Default to UDP / Multicast
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(timeout)
                    # Support broadcast/multicast if requested
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.sendto(data, (target_host, target_port))

            logger.info(
                "CoT event successfully broadcast to tactical edge",
                host=target_host,
                port=target_port,
                proto=protocol,
                bytes=len(data),
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed broadcasting CoT packet to TAK server; tactical edge offline or unreachable",
                host=target_host,
                port=target_port,
                proto=protocol,
                error=str(exc),
            )
            return False

    def dispatch_detection(
        self,
        detection: Dict[str, Any],
        host: Optional[str] = None,
        port: Optional[int] = None,
        proto: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Serialize detection and dispatch to ATAK tactical network."""
        xml_str, uid, cot_type, callsign = self.serialize_cot_xml(detection)
        target_host = host or self.tak_host
        target_port = port or self.tak_port
        protocol = (proto or self.tak_proto).lower()

        success = self.send_socket_payload(
            xml_str, host=target_host, port=target_port, proto=protocol
        )

        det_id = str(detection.get("id") or detection.get("detection_id", ""))
        now_iso = datetime.now(timezone.utc).isoformat()

        # Update cot_broadcast_at in PostGIS if database connection is available
        conn = self.get_connection()
        if conn and det_id:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE infrastructure_detections SET cot_broadcast_at = NOW() WHERE id = %s::uuid;",
                        (det_id,),
                    )
            except Exception as exc:
                logger.debug("Failed updating cot_broadcast_at in PostGIS", error=str(exc))

        return {
            "status": "DISPATCHED" if success else "NETWORK_UNREACHABLE",
            "detection_id": det_id,
            "uid": uid,
            "callsign": callsign,
            "mil_std_2525_type": cot_type,
            "target_host": target_host,
            "target_port": target_port,
            "protocol": protocol,
            "xml_payload": xml_str,
            "timestamp": now_iso,
        }


# Global singleton instance
cot_dispatcher = CoTDispatcher()


@click.command()
@click.option("--id", "det_id", default="det-radar-01", help="Detection ID to broadcast.")
@click.option("--class-name", default="RADAR_DOME", help="Infrastructure class name.")
@click.option("--lon", type=float, default=23.23, help="Longitude coordinate.")
@click.option("--lat", type=float, default=54.14, help="Latitude coordinate.")
@click.option("--host", default=DEFAULT_TAK_HOST, help="TAK Server IP.")
@click.option("--port", type=int, default=DEFAULT_TAK_PORT, help="TAK Server UDP/TCP port.")
def main(det_id: str, class_name: str, lon: float, lat: float, host: str, port: int):
    """Caelum-EO Tactical Edge Cursor-on-Target (CoT) Dispatcher CLI."""
    record = {
        "id": det_id,
        "classification": class_name,
        "coordinates": [lon, lat, 142.5],
        "confidence": 0.96,
        "area_sq_meters": 450.0,
        "zone_id": "suwalki_corridor",
        "reviewer_notes": "Tactical manual CLI broadcast test",
    }
    dispatcher = CoTDispatcher(tak_host=host, tak_port=port)
    result = dispatcher.dispatch_detection(record)
    print("\n=== CURSOR-ON-TARGET (CoT) BROADCAST RESULT ===")
    print(f"STATUS: {result['status']}")
    print(f"UID: {result['uid']} | CALLSIGN: {result['callsign']}")
    print(f"MIL-STD-2525: {result['mil_std_2525_type']}")
    print(f"DESTINATION: {result['target_host']}:{result['target_port']} ({result['protocol']})")
    print("\n--- XML PAYLOAD ---")
    print(result["xml_payload"])


if __name__ == "__main__":
    main()
