"""Vectorization, Polygonization, and PostGIS Persistence Pipeline.

Extracts bounding contours around Prithvi binary change masks using morphological labeling,
converts pixel contours into valid WGS 84 (EPSG:4326) polygons via affine transformations,
classifies the infrastructure via YOLO, and commits intelligence to PostgreSQL 15 / PostGIS 3.3.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import psycopg2
import rasterio.features
import shapely.geometry
import structlog
from pydantic import BaseModel, Field
from rasterio.transform import from_bounds
from scipy import ndimage
from shapely.validation import make_valid

from src.api.service import calculate_priority_score
from src.api.webhooks import dispatch_high_priority_alert
from src.inference.yolo_classifier import YOLOInfrastructureClassifier

logger = structlog.get_logger(__name__)

# Database Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "caelum_geoint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "caelum_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "caelum_secure_password")


class DetectionRecord(BaseModel):
    """Normalized intelligence record matching PostGIS infrastructure_detections table."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    geometry: Dict  # GeoJSON Polygon
    classification: str
    confidence: float
    baseline_timestamp: str
    detection_timestamp: str
    sensor_source: str
    raw_chip_s3_uri: Optional[str] = None
    stac_metadata: Dict = Field(default_factory=dict)
    zone_id: Optional[str] = None
    review_status: str = "PENDING_REVIEW"
    priority_score: float = 0.0
    baseline_chip_path: Optional[str] = None
    detection_chip_path: Optional[str] = None


class PostGISPersistence:
    """Manages spatial database connections and SQL transactions."""

    def __init__(
        self,
        host: str = POSTGRES_HOST,
        port: int = POSTGRES_PORT,
        dbname: str = POSTGRES_DB,
        user: str = POSTGRES_USER,
        password: str = POSTGRES_PASSWORD,
        dry_run: bool = False,
    ):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.dry_run = dry_run
        self._conn = None
        self.committed_records: List[DetectionRecord] = []

    def get_connection(self):
        if self._conn is None and not self.dry_run:
            try:
                self._conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    dbname=self.dbname,
                    user=self.user,
                    password=self.password,
                    connect_timeout=3,
                )
                self._conn.autocommit = True
                logger.info("Connected to PostGIS database", host=self.host, dbname=self.dbname)
            except Exception as exc:
                logger.warning(
                    "PostGIS unavailable; enabling dry-run persistence mode", error=str(exc)
                )
                self.dry_run = True
        return self._conn

    def get_system_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Query a dynamic system configuration value from PostGIS system_configurations."""
        conn = self.get_connection()
        if conn and not self.dry_run:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT value FROM system_configurations WHERE key = %s LIMIT 1;",
                        (key,),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        return str(row[0])
            except Exception as exc:
                logger.debug("Failed fetching configuration from PostGIS", key=key, error=str(exc))
        return default

    def insert_detection(self, record: DetectionRecord) -> bool:
        """Insert detection record into infrastructure_detections with zone lookup and alert dispatch."""
        conn = self.get_connection()

        # If zone_id is not already assigned and live connection is active, spatially look up zone
        zone_alert_level = "NORMAL"
        if conn and not self.dry_run:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, alert_level FROM geographic_zones
                        WHERE ST_Intersects(boundary, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                        LIMIT 1;
                        """,
                        (json.dumps(record.geometry),),
                    )
                    row = cur.fetchone()
                    if row:
                        if not record.zone_id:
                            record.zone_id = str(row[0])
                        zone_alert_level = str(row[1])
            except Exception as exc:
                logger.warning("Failed querying intersecting geographic zone", error=str(exc))

        # Calculate priority score if not set
        if record.priority_score == 0.0:
            record.priority_score = calculate_priority_score(
                confidence=record.confidence,
                classification=record.classification,
                zone_alert_level=zone_alert_level,
            )

        self.committed_records.append(record)

        # Trigger high-priority SIEM alert if threshold exceeded
        if record.priority_score > 0.85:
            try:
                dispatch_high_priority_alert(
                    {
                        "id": record.id,
                        "classification": record.classification,
                        "confidence": record.confidence,
                        "priority_score": record.priority_score,
                        "zone_id": record.zone_id or "UNASSIGNED",
                        "sensor_source": record.sensor_source,
                        "detection_timestamp": record.detection_timestamp,
                    }
                )
            except Exception as exc:
                logger.warning("Failed dispatching high priority alert", error=str(exc))

        if self.dry_run or not conn:
            logger.info(
                "[DRY RUN] Persisted detection to memory ledger",
                id=record.id,
                classification=record.classification,
                confidence=record.confidence,
                priority_score=record.priority_score,
                zone_id=record.zone_id,
            )
            return True

        sql = """
        INSERT INTO infrastructure_detections (
            id,
            geometry,
            classification,
            confidence,
            baseline_timestamp,
            detection_timestamp,
            sensor_source,
            raw_chip_s3_uri,
            stac_metadata,
            zone_id,
            review_status,
            priority_score,
            baseline_chip_path,
            detection_chip_path
        ) VALUES (
            %s,
            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
            %s::infrastructure_class,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s::review_status_enum,
            %s,
            %s,
            %s
        ) ON CONFLICT (id) DO UPDATE SET
            geometry = EXCLUDED.geometry,
            classification = EXCLUDED.classification,
            confidence = EXCLUDED.confidence,
            zone_id = EXCLUDED.zone_id,
            priority_score = EXCLUDED.priority_score,
            review_status = EXCLUDED.review_status;
        """
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        record.id,
                        json.dumps(record.geometry),
                        record.classification,
                        record.confidence,
                        record.baseline_timestamp,
                        record.detection_timestamp,
                        record.sensor_source,
                        record.raw_chip_s3_uri,
                        json.dumps(record.stac_metadata),
                        record.zone_id,
                        record.review_status,
                        record.priority_score,
                        record.baseline_chip_path,
                        record.detection_chip_path,
                    ),
                )
            return True
        except Exception as exc:
            logger.error("Failed executing PostGIS insert", error=str(exc))
            return False


class VectorizationEngine:
    """Polygonizes binary change masks and orchestrates classification & persistence."""

    def __init__(
        self,
        db_handler: Optional[PostGISPersistence] = None,
        min_cluster_pixels: int = 20,
        simplification_tolerance: float = 0.00002,
    ):
        self.db = db_handler or PostGISPersistence()
        self.min_cluster_pixels = min_cluster_pixels
        self.simplification_tol = simplification_tolerance
        self.classifier = YOLOInfrastructureClassifier()

    def polygonize_binary_mask(
        self, binary_mask: np.ndarray, bbox: List[float]
    ) -> List[Tuple[Dict, Tuple[int, int, int, int], int]]:
        """Extract closed GeoJSON polygons from binary mask using affine coordinate transformation.

        Args:
            binary_mask: Uint8 array (H, W).
            bbox: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.

        Returns:
            List of tuples: (geojson_geometry_dict, pixel_bbox, pixel_count).
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        height, width = binary_mask.shape
        affine_transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)

        structure = ndimage.generate_binary_structure(2, 2)
        labeled_mask, num_features = ndimage.label(binary_mask, structure=structure)
        if num_features == 0:
            return []

        slices = ndimage.find_objects(labeled_mask)
        counts = np.bincount(labeled_mask.ravel())

        # Single-pass C-accelerated polygon extraction across all feature clusters
        shapes = rasterio.features.shapes(
            labeled_mask.astype(np.int32),
            mask=(labeled_mask > 0),
            transform=affine_transform,
        )

        polygons = []
        for geom_dict, val in shapes:
            feat_id = int(val)
            pixel_count = int(counts[feat_id])
            if pixel_count < self.min_cluster_pixels:
                continue

            slice_r, slice_c = slices[feat_id - 1]
            pixel_bbox = (
                int(slice_r.start),
                int(slice_c.start),
                int(slice_r.stop - 1),
                int(slice_c.stop - 1),
            )

            poly = shapely.geometry.shape(geom_dict)
            if not poly.is_valid:
                poly = make_valid(poly)

            # Douglas-Peucker topological simplification
            simplified = poly.simplify(self.simplification_tol, preserve_topology=True)
            if simplified.geom_type == "MultiPolygon":
                simplified = max(simplified.geoms, key=lambda p: p.area)

            if simplified.geom_type == "Polygon" and not simplified.is_empty:
                polygons.append((shapely.geometry.mapping(simplified), pixel_bbox, pixel_count))

        logger.info("Polygonized binary change mask", extracted_polygons=len(polygons))
        return polygons

    def process_and_persist(
        self,
        binary_mask: np.ndarray,
        prob_map: np.ndarray,
        full_raster_cube: np.ndarray,
        bbox: List[float],
        baseline_timestamp: str,
        detection_timestamp: str,
        sensor_source: str = "Sentinel-2A-MSI-L2A",
        stac_metadata: Optional[Dict] = None,
    ) -> List[DetectionRecord]:
        """End-to-end vectorization, YOLO classification, and PostGIS commit."""
        extracted_polygons = self.polygonize_binary_mask(binary_mask, bbox)
        records: List[DetectionRecord] = []
        meta = stac_metadata or {}

        # Fetch dynamic ML confidence threshold from DB (default 0.60)
        conf_str = self.db.get_system_config("ml_confidence_threshold", "0.60")
        try:
            min_confidence = float(conf_str) if conf_str else 0.60
        except ValueError:
            min_confidence = 0.60

        for geojson_geom, pixel_bbox, count in extracted_polygons:
            min_r, min_c, max_r, max_c = pixel_bbox
            chip = full_raster_cube[:, min_r : max_r + 1, min_c : max_c + 1]
            mean_prob = float(np.mean(prob_map[min_r : max_r + 1, min_c : max_c + 1]))

            # YOLOv8-OBB classification
            cls_result = self.classifier.classify_cluster(
                chip=chip, bbox=pixel_bbox, pixel_count=count, mean_anomaly_prob=mean_prob
            )

            # Filter out detections below dynamic confidence threshold
            if cls_result.confidence < min_confidence:
                logger.debug(
                    "Filtered out low-confidence detection based on dynamic threshold",
                    confidence=cls_result.confidence,
                    threshold=min_confidence,
                    classification=cls_result.label,
                )
                continue

            record = DetectionRecord(
                geometry=geojson_geom,
                classification=cls_result.label,
                confidence=cls_result.confidence,
                baseline_timestamp=baseline_timestamp,
                detection_timestamp=detection_timestamp,
                sensor_source=sensor_source,
                stac_metadata=meta,
                zone_id=meta.get("zone_id"),
                baseline_chip_path=meta.get("baseline_chip_path"),
                detection_chip_path=meta.get("detection_chip_path"),
            )
            self.db.insert_detection(record)
            records.append(record)

        logger.info("Committed vectorized intelligence", records_count=len(records))
        return records


def run_standalone_pipeline():
    """Execute end-to-end synthetic detection, vectorization, and PostGIS ingestion."""
    from scripts.generate_mock_data import create_synthetic_scene_pair
    from src.inference.prithvi_detector import PrithviChangeDetector

    print("=== Starting Project Caelum-EO Vectorization & Ingestion Pipeline ===")
    detector = PrithviChangeDetector()
    db_handler = PostGISPersistence()
    engine = VectorizationEngine(db_handler=db_handler, min_cluster_pixels=10)

    # 1. Synthesize multi-temporal scene pair
    t0, t1, _ = create_synthetic_scene_pair(height=128, width=128)
    t0_float = t0.astype(np.float32) / 10000.0
    t1_float = t1.astype(np.float32) / 10000.0
    temporal_stack = np.stack([t0_float, t1_float], axis=0)

    # 2. Run Prithvi change detection
    binary_mask, prob_map = detector.detect_changes(temporal_stack, threshold=0.55)
    print(f"Detected {int(np.sum(binary_mask))} change pixels across (128, 128) grid.")

    # 3. Vectorize and commit to PostGIS
    records = engine.process_and_persist(
        binary_mask=binary_mask,
        prob_map=prob_map,
        full_raster_cube=t1_float,
        bbox=[23.10, 54.05, 23.35, 54.25],
        baseline_timestamp="2026-05-15T08:30:00Z",
        detection_timestamp=datetime.now(timezone.utc).isoformat(),
        sensor_source="Sentinel-2A-MSI-L2A",
        stac_metadata={"source": "Caelum-EO Synthetic Ingestion Engine"},
    )
    print(f"Successfully processed and committed {len(records)} infrastructure detection records.")
    for rec in records:
        print(f" - [{rec.classification}] Confidence: {rec.confidence:.1%} (ID: {rec.id})")
    return records


if __name__ == "__main__":
    run_standalone_pipeline()
