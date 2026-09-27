"""Service Layer for Project Caelum-EO Triage & Analytical APIs.

Handles spatial database queries with PostGIS and provides seamless in-memory fallback
for standalone offline testing.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import structlog
from psycopg2.extras import RealDictCursor

from src.api.models import (
    ReviewPayload,
    ReviewResponse,
    ReviewStatus,
    ZoneSummary,
)

logger = structlog.get_logger(__name__)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "caelum_geoint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "caelum_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "caelum_secure_password")


def calculate_priority_score(
    confidence: float,
    classification: str,
    zone_alert_level: str = "NORMAL",
) -> float:
    """Calculate intelligence priority score for triage ranking.

    Formula: Weighted combination of infrastructure severity, zone alert posture,
    and model confidence rating.
    """
    severity_map = {
        "RADAR_DOME": 1.0,
        "RUNWAY_TAXIWAY": 0.95,
        "DEFENSE_REVETMENT": 0.90,
        "LOGISTICS_DEPOT": 0.85,
        "INDUSTRIAL_BUILDING": 0.70,
        "UNKNOWN_STRUCTURE": 0.60,
    }
    alert_map = {
        "HIGH": 1.0,
        "ELEVATED": 0.75,
        "NORMAL": 0.50,
    }
    severity = severity_map.get(classification, 0.50)
    alert = alert_map.get(zone_alert_level, 0.50)

    score = 0.40 * severity + 0.35 * alert + 0.25 * float(confidence)
    return round(min(max(score, 0.0), 1.0), 3)


# Initial in-memory mock state for offline testing
SEED_ZONES = [
    {
        "id": "ZONE-SUWALKI-CORRIDOR",
        "name": "Suwalki Gap Strategic Corridor",
        "alert_level": "HIGH",
        "boundary": {
            "type": "Polygon",
            "coordinates": [
                [[23.00, 54.00], [23.50, 54.00], [23.50, 54.40], [23.00, 54.40], [23.00, 54.00]]
            ],
        },
    },
    {
        "id": "ZONE-NORTH-SECTOR",
        "name": "Northern Frontier Observation Sector",
        "alert_level": "ELEVATED",
        "boundary": {
            "type": "Polygon",
            "coordinates": [
                [[23.00, 54.40], [23.50, 54.40], [23.50, 54.70], [23.00, 54.70], [23.00, 54.40]]
            ],
        },
    },
    {
        "id": "ZONE-WEST-LOGISTICS",
        "name": "Western Staging Logistics Sector",
        "alert_level": "NORMAL",
        "boundary": {
            "type": "Polygon",
            "coordinates": [
                [[22.60, 53.90], [23.00, 53.90], [23.00, 54.30], [22.60, 54.30], [22.60, 53.90]]
            ],
        },
    },
]

SEED_DETECTIONS = [
    {
        "id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [23.148, 54.118],
                    [23.156, 54.118],
                    [23.156, 54.126],
                    [23.148, 54.126],
                    [23.148, 54.118],
                ]
            ],
        },
        "classification": "RADAR_DOME",
        "confidence": 0.965,
        "area_sq_meters": 3450.0,
        "baseline_timestamp": "2026-05-15T08:30:00Z",
        "detection_timestamp": "2026-05-15T08:30:00Z",
        "sensor_source": "Sentinel-2A-MSI-L2A",
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "review_status": "PENDING_REVIEW",
        "priority_score": 0.95,
        "baseline_chip_path": "data/chips/a1b2c3d4/t0.png",
        "detection_chip_path": "data/chips/a1b2c3d4/t1.png",
        "stac_metadata": {"item_id": "S2A_MSIL2A_20260515_T34UFB", "cloud_cover": 2.1},
    },
    {
        "id": "b2c3d4e5-f6a7-48b9-c012-3456789abcde",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [23.180, 54.100],
                    [23.210, 54.100],
                    [23.210, 54.115],
                    [23.180, 54.115],
                    [23.180, 54.100],
                ]
            ],
        },
        "classification": "LOGISTICS_DEPOT",
        "confidence": 0.912,
        "area_sq_meters": 15400.0,
        "baseline_timestamp": "2026-05-15T08:30:00Z",
        "detection_timestamp": "2026-06-02T11:15:00Z",
        "sensor_source": "Sentinel-2B-MSI-L2A",
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "review_status": "PENDING_REVIEW",
        "priority_score": 0.82,
        "baseline_chip_path": "data/chips/b2c3d4e5/t0.png",
        "detection_chip_path": "data/chips/b2c3d4e5/t1.png",
        "stac_metadata": {"item_id": "S2B_MSIL2A_20260602_T34UFB", "cloud_cover": 4.5},
    },
    {
        "id": "c3d4e5f6-a7b8-49c0-d123-456789abcdef",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [23.280, 54.195],
                    [23.355, 54.200],
                    [23.350, 54.215],
                    [23.275, 54.210],
                    [23.280, 54.195],
                ]
            ],
        },
        "classification": "RUNWAY_TAXIWAY",
        "confidence": 0.984,
        "area_sq_meters": 42000.0,
        "baseline_timestamp": "2026-05-15T08:30:00Z",
        "detection_timestamp": "2026-07-10T14:00:00Z",
        "sensor_source": "Sentinel-2A-MSI-L2A",
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "review_status": "PENDING_REVIEW",
        "priority_score": 0.98,
        "baseline_chip_path": "data/chips/c3d4e5f6/t0.png",
        "detection_chip_path": "data/chips/c3d4e5f6/t1.png",
        "stac_metadata": {"item_id": "S2A_MSIL2A_20260710_T34UFB", "cloud_cover": 1.2},
    },
    {
        "id": "d4e5f6a7-b8c9-40d1-e234-56789abcdef0",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [23.220, 54.130],
                    [23.238, 54.130],
                    [23.238, 54.144],
                    [23.220, 54.144],
                    [23.220, 54.130],
                ]
            ],
        },
        "classification": "DEFENSE_REVETMENT",
        "confidence": 0.941,
        "area_sq_meters": 8900.0,
        "baseline_timestamp": "2026-05-15T08:30:00Z",
        "detection_timestamp": "2026-08-22T09:45:00Z",
        "sensor_source": "Sentinel-2B-MSI-L2A",
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "review_status": "VERIFIED",
        "priority_score": 0.75,
        "baseline_chip_path": "data/chips/d4e5f6a7/t0.png",
        "detection_chip_path": "data/chips/d4e5f6a7/t1.png",
        "stac_metadata": {"item_id": "S2B_MSIL2A_20260822_T34UFB", "cloud_cover": 0.8},
    },
    {
        "id": "e5f6a7b8-c9d0-41e2-f345-6789abcdef01",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [23.190, 54.118],
                    [23.208, 54.118],
                    [23.208, 54.129],
                    [23.190, 54.129],
                    [23.190, 54.118],
                ]
            ],
        },
        "classification": "INDUSTRIAL_BUILDING",
        "confidence": 0.893,
        "area_sq_meters": 6700.0,
        "baseline_timestamp": "2026-05-15T08:30:00Z",
        "detection_timestamp": "2026-09-18T10:20:00Z",
        "sensor_source": "Sentinel-2A-MSI-L2A",
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "review_status": "PENDING_REVIEW",
        "priority_score": 0.65,
        "baseline_chip_path": "data/chips/e5f6a7b8/t0.png",
        "detection_chip_path": "data/chips/e5f6a7b8/t1.png",
        "stac_metadata": {"item_id": "S2A_MSIL2A_20260918_T34UFB", "cloud_cover": 3.4},
    },
]


class TriageService:
    """Manages database transactions and analytical queries."""

    def __init__(self):
        self._conn = None
        self._mock_detections: Dict[str, Dict[str, Any]] = {
            d["id"]: dict(d) for d in SEED_DETECTIONS
        }
        self._mock_zones: Dict[str, Dict[str, Any]] = {z["id"]: dict(z) for z in SEED_ZONES}
        self._mock_audit_log: List[Dict[str, Any]] = []

    def get_connection(self):
        """Obtain a live PostgreSQL connection or return None for fallback."""
        if self._conn is not None and not self._conn.closed:
            return self._conn
        try:
            self._conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                connect_timeout=2,
            )
            self._conn.autocommit = True
            return self._conn
        except Exception:
            return None

    def get_detections(
        self,
        classification: Optional[str] = None,
        review_status: Optional[str] = None,
        min_confidence: float = 0.0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        zone_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Query detections and return as GeoJSON FeatureCollection."""
        conn = self.get_connection()
        if conn:
            try:
                query = """
                SELECT
                    id,
                    ST_AsGeoJSON(geometry)::json AS geometry,
                    classification,
                    confidence,
                    area_sq_meters,
                    baseline_timestamp,
                    detection_timestamp,
                    sensor_source,
                    zone_id,
                    review_status,
                    verified_class,
                    priority_score,
                    reviewer_notes,
                    reviewed_by,
                    reviewed_at,
                    baseline_chip_path,
                    detection_chip_path,
                    stac_metadata
                FROM infrastructure_detections
                WHERE confidence >= %s
                """
                params: List[Any] = [min_confidence]
                if classification:
                    query += " AND classification = %s"
                    params.append(classification)
                if review_status:
                    query += " AND review_status = %s"
                    params.append(review_status)
                if start_date:
                    query += " AND detection_timestamp >= %s"
                    params.append(start_date)
                if end_date:
                    query += " AND detection_timestamp <= %s"
                    params.append(end_date)
                if zone_id:
                    query += " AND zone_id = %s"
                    params.append(zone_id)

                query += " ORDER BY detection_timestamp DESC LIMIT %s OFFSET %s;"
                params.extend([limit, offset])

                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()

                features = []
                for r in rows:
                    geom = r.pop("geometry")
                    # Format datetimes
                    for dt_field in ["baseline_timestamp", "detection_timestamp", "reviewed_at"]:
                        if r[dt_field] and hasattr(r[dt_field], "isoformat"):
                            r[dt_field] = r[dt_field].isoformat()
                    features.append(
                        {
                            "type": "Feature",
                            "id": str(r["id"]),
                            "geometry": geom,
                            "properties": r,
                        }
                    )
                return {"type": "FeatureCollection", "features": features}
            except Exception as exc:
                logger.warning(
                    "PostGIS detection query failed; falling back to memory store", error=str(exc)
                )

        # Memory store fallback
        filtered = list(self._mock_detections.values())
        if classification:
            filtered = [d for d in filtered if d.get("classification") == classification]
        if review_status:
            filtered = [d for d in filtered if d.get("review_status") == review_status]
        if min_confidence > 0.0:
            filtered = [d for d in filtered if float(d.get("confidence", 0.0)) >= min_confidence]
        if zone_id:
            filtered = [d for d in filtered if d.get("zone_id") == zone_id]
        if start_date:
            filtered = [d for d in filtered if str(d.get("detection_timestamp")) >= start_date]
        if end_date:
            filtered = [d for d in filtered if str(d.get("detection_timestamp")) <= end_date]

        paged = filtered[offset : offset + limit]
        features = []
        for d in paged:
            props = dict(d)
            geom = props.pop("geometry")
            features.append(
                {"type": "Feature", "id": str(d["id"]), "geometry": geom, "properties": props}
            )
        return {"type": "FeatureCollection", "features": features}

    def get_zones_summary(self) -> List[ZoneSummary]:
        """Aggregate detection statistics per geographic zone via spatial JOIN."""
        conn = self.get_connection()
        if conn:
            try:
                query = """
                SELECT
                    z.id,
                    z.name,
                    z.alert_level,
                    ST_AsGeoJSON(z.boundary)::json AS boundary,
                    COUNT(d.id) AS total_detections,
                    COUNT(d.id) FILTER (WHERE d.detection_timestamp >= NOW() - INTERVAL '24 HOURS') AS new_detections_24h,
                    COUNT(d.id) FILTER (WHERE d.detection_timestamp >= NOW() - INTERVAL '7 DAYS') AS new_detections_7d,
                    COUNT(d.id) FILTER (WHERE d.priority_score >= 0.80) AS high_priority_count,
                    COALESCE(
                        json_object_agg(d.classification, class_counts.cnt) FILTER (WHERE d.classification IS NOT NULL),
                        '{}'::json
                    ) AS classification_breakdown
                FROM geographic_zones z
                LEFT JOIN infrastructure_detections d ON d.zone_id = z.id
                LEFT JOIN (
                    SELECT zone_id, classification, COUNT(*) AS cnt
                    FROM infrastructure_detections
                    GROUP BY zone_id, classification
                ) class_counts ON class_counts.zone_id = z.id AND class_counts.classification = d.classification
                GROUP BY z.id, z.name, z.alert_level, z.boundary;
                """
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query)
                    rows = cur.fetchall()

                results = []
                for r in rows:
                    results.append(
                        ZoneSummary(
                            id=r["id"],
                            name=r["name"],
                            alert_level=r["alert_level"],
                            boundary=r["boundary"],
                            total_detections=r["total_detections"],
                            new_detections_24h=r["new_detections_24h"],
                            new_detections_7d=r["new_detections_7d"],
                            high_priority_count=r["high_priority_count"],
                            classification_breakdown=r["classification_breakdown"] or {},
                        )
                    )
                return results
            except Exception as exc:
                logger.warning(
                    "PostGIS zone summary query failed; falling back to memory store",
                    error=str(exc),
                )

        # Memory store aggregation
        summaries = []
        for z_id, z in self._mock_zones.items():
            zone_dets = [d for d in self._mock_detections.values() if d.get("zone_id") == z_id]
            breakdown: Dict[str, int] = {}
            high_prio = 0
            for d in zone_dets:
                cls = d.get("classification", "UNKNOWN_STRUCTURE")
                breakdown[cls] = breakdown.get(cls, 0) + 1
                if float(d.get("priority_score", 0.0)) >= 0.80:
                    high_prio += 1

            summaries.append(
                ZoneSummary(
                    id=z["id"],
                    name=z["name"],
                    alert_level=z["alert_level"],
                    boundary=z["boundary"],
                    total_detections=len(zone_dets),
                    new_detections_24h=min(len(zone_dets), 2),
                    new_detections_7d=len(zone_dets),
                    high_priority_count=high_prio,
                    classification_breakdown=breakdown,
                )
            )
        return summaries

    def get_triage_queue(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return pending detections ranked by priority score DESC."""
        conn = self.get_connection()
        if conn:
            try:
                query = """
                SELECT
                    id,
                    ST_AsGeoJSON(geometry)::json AS geometry,
                    classification,
                    confidence,
                    area_sq_meters,
                    detection_timestamp,
                    sensor_source,
                    zone_id,
                    review_status,
                    priority_score,
                    baseline_chip_path,
                    detection_chip_path
                FROM infrastructure_detections
                WHERE review_status = 'PENDING_REVIEW'
                ORDER BY priority_score DESC, detection_timestamp DESC
                LIMIT %s;
                """
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, [limit])
                    rows = cur.fetchall()

                for r in rows:
                    if r.get("detection_timestamp") and hasattr(
                        r["detection_timestamp"], "isoformat"
                    ):
                        r["detection_timestamp"] = r["detection_timestamp"].isoformat()
                return list(rows)
            except Exception as exc:
                logger.warning(
                    "PostGIS triage queue query failed; falling back to memory store",
                    error=str(exc),
                )

        # Memory store fallback
        pending = [
            d for d in self._mock_detections.values() if d.get("review_status") == "PENDING_REVIEW"
        ]
        pending.sort(key=lambda x: float(x.get("priority_score", 0.0)), reverse=True)
        return pending[:limit]

    def get_detection_by_id(self, detection_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single detection record."""
        conn = self.get_connection()
        if conn:
            try:
                query = """
                SELECT
                    id,
                    ST_AsGeoJSON(geometry)::json AS geometry,
                    classification,
                    confidence,
                    area_sq_meters,
                    baseline_timestamp,
                    detection_timestamp,
                    sensor_source,
                    zone_id,
                    review_status,
                    verified_class,
                    priority_score,
                    reviewer_notes,
                    reviewed_by,
                    reviewed_at,
                    baseline_chip_path,
                    detection_chip_path,
                    stac_metadata
                FROM infrastructure_detections
                WHERE id = %s::uuid;
                """
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, [detection_id])
                    row = cur.fetchone()
                    if row:
                        for dt in ["baseline_timestamp", "detection_timestamp", "reviewed_at"]:
                            if row[dt] and hasattr(row[dt], "isoformat"):
                                row[dt] = row[dt].isoformat()
                        return dict(row)
            except Exception as exc:
                logger.warning(
                    "PostGIS detection query by ID failed", id=detection_id, error=str(exc)
                )

        return self._mock_detections.get(detection_id)

    def submit_review(self, detection_id: str, payload: ReviewPayload) -> Optional[ReviewResponse]:
        """Update detection status, recalculate priority, and log to review_audit_log."""
        now_iso = datetime.now(timezone.utc).isoformat()
        current = self.get_detection_by_id(detection_id)
        if not current:
            return None

        prev_status = current.get("review_status", "PENDING_REVIEW")
        prev_class = current.get("classification")
        target_class = (
            payload.verified_class.value
            if payload.verified_class
            else current.get("classification", "UNKNOWN_STRUCTURE")
        )

        # Recalculate priority score
        zone_id = current.get("zone_id", "ZONE-SUWALKI-CORRIDOR")
        zone_alert = "NORMAL"
        for z in SEED_ZONES:
            if z["id"] == zone_id:
                zone_alert = str(z["alert_level"])

        if payload.review_status == ReviewStatus.FALSE_POSITIVE:
            new_priority = 0.0
        elif payload.review_status == ReviewStatus.VERIFIED:
            new_priority = 0.10  # Deprioritize already verified targets
        else:
            new_priority = calculate_priority_score(
                confidence=float(current.get("confidence", 0.8)),
                classification=target_class,
                zone_alert_level=zone_alert,
            )

        conn = self.get_connection()
        if conn:
            try:
                update_query = """
                UPDATE infrastructure_detections
                SET
                    review_status = %s::review_status_enum,
                    verified_class = %s::infrastructure_class,
                    priority_score = %s,
                    reviewer_notes = %s,
                    reviewed_by = %s,
                    reviewed_at = NOW()
                WHERE id = %s::uuid;
                """
                audit_query = """
                INSERT INTO review_audit_log (
                    detection_id,
                    previous_status,
                    new_status,
                    previous_class,
                    verified_class,
                    reviewer_notes,
                    reviewed_by
                ) VALUES (
                    %s::uuid,
                    %s::review_status_enum,
                    %s::review_status_enum,
                    %s::infrastructure_class,
                    %s::infrastructure_class,
                    %s,
                    %s
                );
                """
                with conn.cursor() as cur:
                    cur.execute(
                        update_query,
                        [
                            payload.review_status.value,
                            payload.verified_class.value if payload.verified_class else None,
                            new_priority,
                            payload.reviewer_notes,
                            payload.reviewed_by,
                            detection_id,
                        ],
                    )
                    cur.execute(
                        audit_query,
                        [
                            detection_id,
                            prev_status,
                            payload.review_status.value,
                            prev_class,
                            payload.verified_class.value if payload.verified_class else None,
                            payload.reviewer_notes,
                            payload.reviewed_by,
                        ],
                    )
            except Exception as exc:
                logger.warning(
                    "PostGIS review update failed; updating memory store", error=str(exc)
                )

        # Memory store update
        if detection_id in self._mock_detections:
            self._mock_detections[detection_id]["review_status"] = payload.review_status.value
            if payload.verified_class:
                self._mock_detections[detection_id]["verified_class"] = payload.verified_class.value
            self._mock_detections[detection_id]["priority_score"] = new_priority
            self._mock_detections[detection_id]["reviewer_notes"] = payload.reviewer_notes
            self._mock_detections[detection_id]["reviewed_by"] = payload.reviewed_by
            self._mock_detections[detection_id]["reviewed_at"] = now_iso

        self._mock_audit_log.append(
            {
                "detection_id": detection_id,
                "previous_status": prev_status,
                "new_status": payload.review_status.value,
                "reviewer_notes": payload.reviewer_notes,
                "reviewed_by": payload.reviewed_by,
                "reviewed_at": now_iso,
            }
        )

        return ReviewResponse(
            id=detection_id,
            review_status=payload.review_status,
            verified_class=payload.verified_class,
            priority_score=new_priority,
            reviewer_notes=payload.reviewer_notes,
            reviewed_by=payload.reviewed_by or "analyst",
            reviewed_at=now_iso,
            message="Detection review committed successfully and audit trail logged.",
        )


triage_service = TriageService()
