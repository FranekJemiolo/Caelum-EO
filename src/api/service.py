"""Service Layer for Project Caelum-EO Triage & Analytical APIs.

Handles spatial database queries with PostGIS and provides seamless in-memory fallback
for standalone offline testing.
"""

import csv
import io
import json
import os
import uuid
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
        self._mock_configs: Dict[str, Dict[str, Any]] = {
            "ml_confidence_threshold": {
                "id": 1,
                "key": "ml_confidence_threshold",
                "value": "0.60",
                "description": "Minimum inference confidence score required to ingest detection into intelligence store",
                "updated_by": None,
                "updated_at": "2026-09-28T12:00:00Z",
            },
            "stac_polling_interval_seconds": {
                "id": 2,
                "key": "stac_polling_interval_seconds",
                "value": "300",
                "description": "STAC catalog ingestion polling frequency in seconds",
                "updated_by": None,
                "updated_at": "2026-09-28T12:00:00Z",
            },
            "dlq_topic": {
                "id": 3,
                "key": "dlq_topic",
                "value": "caelum.dlq",
                "description": "Kafka Dead Letter Queue topic name for unparseable or failed messages",
                "updated_by": None,
                "updated_at": "2026-09-28T12:00:00Z",
            },
            "webhook_url": {
                "id": 4,
                "key": "webhook_url",
                "value": "http://localhost:8000/api/v1/webhooks/alerts",
                "description": "Local webhook endpoint for critical GEOINT triage alerts",
                "updated_by": None,
                "updated_at": "2026-09-28T12:00:00Z",
            },
            "target_geofences": {
                "id": 5,
                "key": "target_geofences",
                "value": json.dumps(
                    [
                        {"name": "Suwalki Corridor", "bbox": [23.00, 54.00, 23.50, 54.40]},
                        {"name": "Northern Frontier", "bbox": [23.00, 54.40, 23.50, 54.70]},
                        {"name": "Western Logistics", "bbox": [22.60, 53.90, 23.00, 54.30]},
                    ]
                ),
                "description": "Target geographic bounding boxes (geofences) actively polled by STAC collectors",
                "updated_by": None,
                "updated_at": "2026-09-28T12:00:00Z",
            },
        }
        self._mock_comments: List[Dict[str, Any]] = [
            {
                "id": "c1111111-2222-3333-4444-555555555555",
                "detection_id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
                "user_id": "00000000-0000-0000-0000-000000000002",
                "username": "analyst_viper",
                "comment": "Target shows geometric signature characteristic of mobile radar telemetry dome. Cross-referencing EW logs.",
                "created_at": "2026-05-15T09:12:00Z",
            }
        ]
        self._mock_detection_audit: List[Dict[str, Any]] = [
            {
                "id": "d1111111-2222-3333-4444-555555555555",
                "detection_id": "d4e5f6a7-b8c9-40d1-e234-56789abcdef0",
                "previous_state": "PENDING_REVIEW",
                "new_state": "VERIFIED",
                "user_id": "00000000-0000-0000-0000-000000000002",
                "username": "analyst_viper",
                "note": "Revetment structure confirmed by secondary multi-spectral analysis.",
                "timestamp": "2026-08-22T10:00:00Z",
            }
        ]
        self._mock_saved_filters: Dict[str, List[Dict[str, Any]]] = {}

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
                    detection_audit_query = """
                    INSERT INTO detection_audit_log (
                        detection_id,
                        previous_state,
                        new_state,
                        user_id,
                        username,
                        note
                    ) VALUES (
                        %s::uuid,
                        %s,
                        %s,
                        NULL,
                        %s,
                        %s
                    );
                    """
                    cur.execute(
                        detection_audit_query,
                        [
                            detection_id,
                            prev_status,
                            payload.review_status.value,
                            payload.reviewed_by or "analyst",
                            payload.reviewer_notes,
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
        self._mock_detection_audit.append(
            {
                "id": str(uuid.uuid4()),
                "detection_id": detection_id,
                "previous_state": prev_status,
                "new_state": payload.review_status.value,
                "user_id": None,
                "username": payload.reviewed_by or "analyst",
                "note": payload.reviewer_notes,
                "timestamp": now_iso,
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

    def get_audit_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent verification audit log records for active learning."""
        conn = self.get_connection()
        if not conn:
            return list(reversed(self._mock_audit_log))[:limit]

        query = """
            SELECT
                detection_id,
                previous_status,
                new_status,
                previous_class,
                new_class,
                reviewer_notes,
                reviewed_by,
                reviewed_at
            FROM review_audit_log
            ORDER BY reviewed_at DESC
            LIMIT %s;
        """
        try:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                if cur.description:
                    cols = [desc[0] for desc in cur.description]
                    return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
                return []
        except Exception as exc:
            logger.warning("Failed querying review_audit_log table", error=str(exc))
            return list(reversed(self._mock_audit_log))[:limit]

    # =========================================================================
    # Version 3: Dynamic System Configuration
    # =========================================================================

    def get_configurations(self) -> List[Dict[str, Any]]:
        """Retrieve all dynamic system configuration settings."""
        conn = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, key, value, description, updated_by::text, updated_at "
                        "FROM system_configurations ORDER BY key ASC;"
                    )
                    if cur.description:
                        cols = [desc[0] for desc in cur.description]
                        return [
                            {
                                **dict(zip(cols, row, strict=False)),
                                "updated_at": row[cols.index("updated_at")].isoformat()
                                if row[cols.index("updated_at")]
                                else None,
                            }
                            for row in cur.fetchall()
                        ]
            except Exception as exc:
                logger.warning("Failed querying system_configurations table", error=str(exc))

        return list(self._mock_configs.values())

    def get_configuration(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific configuration by its key."""
        conn = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, key, value, description, updated_by::text, updated_at "
                        "FROM system_configurations WHERE key = %s;",
                        (key,),
                    )
                    row = cur.fetchone()
                    if row and cur.description:
                        cols = [desc[0] for desc in cur.description]
                        res = dict(zip(cols, row, strict=False))
                        if res.get("updated_at"):
                            res["updated_at"] = res["updated_at"].isoformat()
                        return res
            except Exception as exc:
                logger.warning(
                    "Failed querying system_configurations for key", key=key, error=str(exc)
                )

        return self._mock_configs.get(key)

    def set_configuration(
        self,
        key: str,
        value: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update or insert a dynamic configuration setting."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        if conn:
            try:
                query = """
                INSERT INTO system_configurations (key, value, description, updated_by, updated_at)
                VALUES (%s, %s, %s, %s::uuid, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    description = COALESCE(EXCLUDED.description, system_configurations.description),
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                RETURNING id, key, value, description, updated_by::text, updated_at;
                """
                with conn.cursor() as cur:
                    cur.execute(query, (key, value, description, user_id))
                    row = cur.fetchone()
                    if row and cur.description:
                        cols = [desc[0] for desc in cur.description]
                        res = dict(zip(cols, row, strict=False))
                        if res.get("updated_at"):
                            res["updated_at"] = res["updated_at"].isoformat()
                        self._mock_configs[key] = res
                        return res
            except Exception as exc:
                logger.warning("Failed updating system_configuration", key=key, error=str(exc))

        existing = self._mock_configs.get(key, {})
        item = {
            "id": existing.get("id", len(self._mock_configs) + 1),
            "key": key,
            "value": value,
            "description": description or existing.get("description", ""),
            "updated_by": user_id,
            "updated_at": now_iso,
        }
        self._mock_configs[key] = item
        return item

    # =========================================================================
    # Version 3: Analyst Collaboration & Threaded Notes
    # =========================================================================

    def get_comments(self, detection_id: str) -> List[Dict[str, Any]]:
        """Retrieve chronological threaded analyst notes for a detection."""
        conn = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id::text, detection_id::text, user_id::text, username, comment, created_at "
                        "FROM detection_comments WHERE detection_id = %s::uuid "
                        "ORDER BY created_at ASC;",
                        (detection_id,),
                    )
                    if cur.description:
                        cols = [desc[0] for desc in cur.description]
                        return [
                            {
                                **dict(zip(cols, row, strict=False)),
                                "created_at": row[cols.index("created_at")].isoformat()
                                if row[cols.index("created_at")]
                                else "",
                            }
                            for row in cur.fetchall()
                        ]
            except Exception as exc:
                logger.warning("Failed querying detection_comments", error=str(exc))

        return [c for c in self._mock_comments if c["detection_id"] == detection_id]

    def add_comment(
        self,
        detection_id: str,
        comment: str,
        username: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add an analyst note to a detection thread."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        if conn:
            try:
                query = """
                INSERT INTO detection_comments (detection_id, user_id, username, comment)
                VALUES (%s::uuid, %s::uuid, %s, %s)
                RETURNING id::text, detection_id::text, user_id::text, username, comment, created_at;
                """
                with conn.cursor() as cur:
                    cur.execute(query, (detection_id, user_id, username, comment))
                    row = cur.fetchone()
                    if row and cur.description:
                        cols = [desc[0] for desc in cur.description]
                        res = dict(zip(cols, row, strict=False))
                        if res.get("created_at"):
                            res["created_at"] = res["created_at"].isoformat()
                        self._mock_comments.append(res)
                        return res
            except Exception as exc:
                logger.warning("Failed inserting into detection_comments", error=str(exc))

        new_entry = {
            "id": str(uuid.uuid4()),
            "detection_id": detection_id,
            "user_id": user_id,
            "username": username,
            "comment": comment,
            "created_at": now_iso,
        }
        self._mock_comments.append(new_entry)
        return new_entry

    # =========================================================================
    # Version 3: Audit History Timeline
    # =========================================================================

    def get_detection_audit_trail(self, detection_id: str) -> List[Dict[str, Any]]:
        """Retrieve complete state change audit trail for a specific detection."""
        conn = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id::text, detection_id::text, previous_state, new_state, "
                        "user_id::text, username, note, timestamp "
                        "FROM detection_audit_log WHERE detection_id = %s::uuid "
                        "ORDER BY timestamp ASC;",
                        (detection_id,),
                    )
                    if cur.description:
                        cols = [desc[0] for desc in cur.description]
                        return [
                            {
                                **dict(zip(cols, row, strict=False)),
                                "timestamp": row[cols.index("timestamp")].isoformat()
                                if row[cols.index("timestamp")]
                                else "",
                            }
                            for row in cur.fetchall()
                        ]
            except Exception as exc:
                logger.warning("Failed querying detection_audit_log", error=str(exc))

        return [a for a in self._mock_detection_audit if a["detection_id"] == detection_id]

    def log_detection_audit(
        self,
        detection_id: str,
        previous_state: Optional[str],
        new_state: str,
        username: str,
        user_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record detection transition event into audit log."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        if conn:
            try:
                query = """
                INSERT INTO detection_audit_log (detection_id, previous_state, new_state, user_id, username, note)
                VALUES (%s::uuid, %s, %s, %s::uuid, %s, %s)
                RETURNING id::text, detection_id::text, previous_state, new_state, user_id::text, username, note, timestamp;
                """
                with conn.cursor() as cur:
                    cur.execute(
                        query, (detection_id, previous_state, new_state, user_id, username, note)
                    )
                    row = cur.fetchone()
                    if row and cur.description:
                        cols = [desc[0] for desc in cur.description]
                        res = dict(zip(cols, row, strict=False))
                        if res.get("timestamp"):
                            res["timestamp"] = res["timestamp"].isoformat()
                        self._mock_detection_audit.append(res)
                        return res
            except Exception as exc:
                logger.warning("Failed inserting into detection_audit_log", error=str(exc))

        record = {
            "id": str(uuid.uuid4()),
            "detection_id": detection_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "user_id": user_id,
            "username": username,
            "note": note,
            "timestamp": now_iso,
        }
        self._mock_detection_audit.append(record)
        return record

    # =========================================================================
    # Version 3: Saved Views & Advanced Filtering
    # =========================================================================

    def get_saved_filters(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve saved filter views for a specific analyst user."""
        conn = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id::text, user_id::text, name, filter_json, created_at "
                        "FROM saved_filters WHERE user_id = %s::uuid "
                        "ORDER BY created_at DESC;",
                        (user_id,),
                    )
                    if cur.description:
                        cols = [desc[0] for desc in cur.description]
                        return [
                            {
                                **dict(zip(cols, row, strict=False)),
                                "created_at": row[cols.index("created_at")].isoformat()
                                if row[cols.index("created_at")]
                                else "",
                            }
                            for row in cur.fetchall()
                        ]
            except Exception as exc:
                logger.warning("Failed querying saved_filters", error=str(exc))

        return self._mock_saved_filters.get(user_id, [])

    def create_saved_filter(
        self,
        user_id: str,
        name: str,
        filter_json: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Save a new filter preset for an analyst."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        if conn:
            try:
                query = """
                INSERT INTO saved_filters (user_id, name, filter_json)
                VALUES (%s::uuid, %s, %s::jsonb)
                RETURNING id::text, user_id::text, name, filter_json, created_at;
                """
                with conn.cursor() as cur:
                    cur.execute(query, (user_id, name, json.dumps(filter_json)))
                    row = cur.fetchone()
                    if row and cur.description:
                        cols = [desc[0] for desc in cur.description]
                        res = dict(zip(cols, row, strict=False))
                        if res.get("created_at"):
                            res["created_at"] = res["created_at"].isoformat()
                        user_list = self._mock_saved_filters.setdefault(user_id, [])
                        user_list.append(res)
                        return res
            except Exception as exc:
                logger.warning("Failed creating saved_filter", error=str(exc))

        new_filter = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name,
            "filter_json": filter_json,
            "created_at": now_iso,
        }
        user_list = self._mock_saved_filters.setdefault(user_id, [])
        user_list.insert(0, new_filter)
        return new_filter

    def delete_saved_filter(self, user_id: str, filter_id: str) -> bool:
        """Delete a saved filter preset."""
        conn = self.get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM saved_filters WHERE id = %s::uuid AND user_id = %s::uuid;",
                        (filter_id, user_id),
                    )
            except Exception as exc:
                logger.warning("Failed deleting saved_filter", error=str(exc))

        if user_id in self._mock_saved_filters:
            original_len = len(self._mock_saved_filters[user_id])
            self._mock_saved_filters[user_id] = [
                f for f in self._mock_saved_filters[user_id] if f["id"] != filter_id
            ]
            return len(self._mock_saved_filters[user_id]) < original_len
        return True

    # =========================================================================
    # Version 3: Intelligence Export & Reporting Engine
    # =========================================================================

    def export_detections(
        self,
        detection_ids: Optional[List[str]] = None,
        zone_id: Optional[str] = None,
        format: str = "geojson",
    ) -> tuple[str, str, str]:
        """Export detections to GeoJSON (for military GIS/ATAK) or CSV summary.

        Returns: (content_string, media_type, filename)
        """
        all_detections_res = self.get_detections(limit=1000)
        features = all_detections_res.get("features", [])

        # Filter by detection IDs if specified
        if detection_ids:
            id_set = set(detection_ids)
            features = [
                f
                for f in features
                if f.get("id") in id_set or f.get("properties", {}).get("id") in id_set
            ]

        # Filter by zone if specified
        if zone_id:
            features = [f for f in features if f.get("properties", {}).get("zone_id") == zone_id]

        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "id",
                    "classification",
                    "confidence",
                    "area_sq_meters",
                    "review_status",
                    "verified_class",
                    "priority_score",
                    "zone_id",
                    "detection_timestamp",
                    "baseline_timestamp",
                    "sensor_source",
                    "latitude",
                    "longitude",
                    "reviewer_notes",
                    "reviewed_by",
                    "reviewed_at",
                ]
            )

            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                lat_str, lon_str = "", ""
                if (
                    geom
                    and geom.get("type") == "Polygon"
                    and geom.get("coordinates")
                    and len(geom["coordinates"]) > 0
                ):
                    ring = geom["coordinates"][0]
                    if ring:
                        lon = round(sum(p[0] for p in ring) / len(ring), 6)
                        lat = round(sum(p[1] for p in ring) / len(ring), 6)
                        lat_str, lon_str = str(lat), str(lon)

                writer.writerow(
                    [
                        feat.get("id") or props.get("id", ""),
                        props.get("classification", ""),
                        props.get("confidence", ""),
                        props.get("area_sq_meters", ""),
                        props.get("review_status", ""),
                        props.get("verified_class", "") or "",
                        props.get("priority_score", ""),
                        props.get("zone_id", "") or "",
                        props.get("detection_timestamp", ""),
                        props.get("baseline_timestamp", ""),
                        props.get("sensor_source", ""),
                        lat_str,
                        lon_str,
                        props.get("reviewer_notes", "") or "",
                        props.get("reviewed_by", "") or "",
                        props.get("reviewed_at", "") or "",
                    ]
                )

            return output.getvalue(), "text/csv", "caelum_detections_export.csv"

        # GeoJSON export (RFC 7946)
        export_geojson = {
            "type": "FeatureCollection",
            "metadata": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "system": "Project Caelum-EO GEOINT Platform",
                "version": "3.0.0",
                "total_features": len(features),
            },
            "features": features,
        }
        return (
            json.dumps(export_geojson, indent=2),
            "application/geo+json",
            "caelum_detections_export.geojson",
        )

    # =========================================================================
    # Version 4: 3D Terrain Viewshed & Line-of-Sight Analytics
    # =========================================================================

    def calculate_viewshed(
        self,
        detection_id: Optional[str] = None,
        lon: Optional[float] = None,
        lat: Optional[float] = None,
        observer_height: float = 15.0,
        target_height: float = 2.0,
        max_radius_km: float = 12.0,
    ) -> Dict[str, Any]:
        """Calculate radar line-of-sight viewshed over 3D Digital Elevation Model (DEM)."""
        from shapely.geometry import shape

        from src.analytics.viewshed import calculate_radar_viewshed

        obs_lon = lon
        obs_lat = lat

        if detection_id:
            # Query detection geometry
            det = self.get_detection_by_id(detection_id)
            if det and "geometry" in det:
                geom = shape(det["geometry"])
                centroid = geom.centroid
                obs_lon = float(centroid.x)
                obs_lat = float(centroid.y)

        if obs_lon is None or obs_lat is None:
            # Default to Suwalki Corridor strategic center
            obs_lon = 23.15
            obs_lat = 54.12

        viewshed_feat = calculate_radar_viewshed(
            lon=obs_lon,
            lat=obs_lat,
            observer_height=observer_height,
            target_height=target_height,
            max_radius_km=max_radius_km,
        )

        if detection_id:
            viewshed_feat["properties"]["detection_id"] = detection_id

        # Cache in viewshed_calculations table if live connection exists
        conn = self.get_connection()
        if conn and detection_id:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO viewshed_calculations (
                            detection_id, observer_lon, observer_lat, observer_elevation_msl,
                            antenna_height_m, radius_km, geometry, visible_area_sq_km, coverage_percentage
                        ) VALUES (
                            %s::uuid, %s, %s, %s, %s, %s,
                            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s
                        );
                        """,
                        (
                            detection_id,
                            obs_lon,
                            obs_lat,
                            viewshed_feat["properties"].get("observer_elevation_msl", 165.0),
                            observer_height,
                            max_radius_km,
                            json.dumps(viewshed_feat["geometry"]),
                            viewshed_feat["properties"].get("visible_area_sq_km", 0.0),
                            viewshed_feat["properties"].get("coverage_percentage", 0.0),
                        ),
                    )
            except Exception as exc:
                logger.warning("Failed caching viewshed calculation in PostGIS", error=str(exc))

        return viewshed_feat


triage_service = TriageService()
