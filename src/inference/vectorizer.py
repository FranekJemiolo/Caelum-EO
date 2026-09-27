"""Vectorization, Classification, and PostGIS Storage Pipeline.

Isolates bounding boxes of detected structural changes from the Prithvi binary mask,
simulates classification via YOLOv8-OBB and zero-shot perimeter extraction via GeoSAM,
and persists vectorized intelligence into PostgreSQL 15 / PostGIS 3.3.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import click
import numpy as np
from pydantic import BaseModel, Field
from scipy import ndimage
import shapely.geometry
from shapely.validation import make_valid
import structlog

logger = structlog.get_logger(__name__)

# Database Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "caelum_geoint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "caelum_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "caelum_secure_password")

# Supported Classification Taxonomy
TARGET_CLASSES = [
    "Logistics_Depot",
    "Radar_Dome",
    "Airfield_Runway",
    "SAM_Battery_Site",
    "Hardened_Shelter",
    "Naval_Pier_Berth",
    "Fuel_Storage_Tank",
    "Unknown_Structure"
]


class AnomalyBBox(BaseModel):
    """Bounding box and centroid of an isolated anomaly cluster."""
    cluster_id: int
    pixel_bbox: Tuple[int, int, int, int]  # (min_r, min_c, max_r, max_c)
    pixel_centroid: Tuple[float, float]    # (row, col)
    pixel_count: int


class VectorizedDetection(BaseModel):
    """Normalized payload ready for PostGIS insertion."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    geometry_geojson: Dict
    classification: str
    confidence: float
    detection_date: str
    source_imagery: Dict


class PostGISWriter:
    """Manages database connections and spatial insertions using psycopg2."""

    def __init__(
        self,
        host: str = POSTGRES_HOST,
        port: int = POSTGRES_PORT,
        dbname: str = POSTGRES_DB,
        user: str = POSTGRES_USER,
        password: str = POSTGRES_PASSWORD,
        dry_run: bool = False
    ):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.dry_run = dry_run
        self._connection = None

    def get_connection(self):
        """Lazy database connection initialization."""
        if self._connection is None and not self.dry_run:
            try:
                import psycopg2
                logger.info("Connecting to PostGIS database", host=self.host, port=self.port, db=self.dbname)
                self._connection = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    dbname=self.dbname,
                    user=self.user,
                    password=self.password,
                    connect_timeout=5
                )
                self._connection.autocommit = True
            except Exception as exc:
                logger.warning(
                    "Could not connect to live PostGIS, operating in dry-run logging mode",
                    error=str(exc)
                )
                self.dry_run = True
        return self._connection

    def insert_detection(self, detection: VectorizedDetection) -> bool:
        """Insert a single detection record into PostGIS 'infrastructure_detections'."""
        if self.dry_run:
            logger.info(
                "[DRY RUN] PostGIS Insert",
                id=detection.id,
                classification=detection.classification,
                confidence=detection.confidence,
                vertices=len(detection.geometry_geojson.get("coordinates", [[]])[0])
            )
            return True

        conn = self.get_connection()
        if not conn:
            return False

        insert_sql = """
        INSERT INTO infrastructure_detections (
            id, geometry, classification, confidence, detection_date, source_imagery
        ) VALUES (
            %s,
            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
            %s,
            %s,
            %s,
            %s
        ) ON CONFLICT (id) DO NOTHING;
        """
        try:
            with conn.cursor() as cur:
                cur.execute(
                    insert_sql,
                    (
                        detection.id,
                        json.dumps(detection.geometry_geojson),
                        detection.classification,
                        detection.confidence,
                        detection.detection_date,
                        json.dumps(detection.source_imagery)
                    )
                )
            logger.debug("Persisted detection to PostGIS", id=detection.id)
            return True
        except Exception as exc:
            logger.error("PostGIS insertion failed", id=detection.id, error=str(exc))
            return False

    def insert_batch(self, detections: List[VectorizedDetection]) -> int:
        """Insert a batch of detections."""
        count = 0
        for d in detections:
            if self.insert_detection(d):
                count += 1
        return count


class VectorizationPipeline:
    """Takes Prithvi binary mask, runs YOLO-OBB & GeoSAM simulation, and stores in PostGIS."""

    def __init__(self, db_writer: Optional[PostGISWriter] = None, min_cluster_size: int = 20):
        self.db_writer = db_writer or PostGISWriter()
        self.min_cluster_size = min_cluster_size

    def isolate_bounding_boxes(self, binary_mask: np.ndarray) -> List[AnomalyBBox]:
        """Isolate spatial bounding boxes for clusters of 1s in the binary mask."""
        structure = ndimage.generate_binary_structure(2, 2)
        labeled_mask, num_features = ndimage.label(binary_mask, structure=structure)

        bboxes: List[AnomalyBBox] = []
        for feature_id in range(1, num_features + 1):
            coords = np.argwhere(labeled_mask == feature_id)
            if len(coords) < self.min_cluster_size:
                continue

            min_r, min_c = coords.min(axis=0)
            max_r, max_c = coords.max(axis=0)
            cr, cc = coords.mean(axis=0)

            bbox = AnomalyBBox(
                cluster_id=feature_id,
                pixel_bbox=(int(min_r), int(min_c), int(max_r), int(max_c)),
                pixel_centroid=(float(cr), float(cc)),
                pixel_count=len(coords)
            )
            bboxes.append(bbox)

        logger.info(
            "Isolated change bounding boxes",
            total_labeled=num_features,
            retained_boxes=len(bboxes)
        )
        return bboxes

    def simulate_yolo_and_geosam(
        self,
        bbox: AnomalyBBox,
        geo_bounds: List[float],
        raster_shape: Tuple[int, int]
    ) -> Tuple[str, float, Dict]:
        """Simulate YOLOv8-OBB classification and GeoSAM zero-shot perimeter polygon extraction.

        Args:
            bbox: Isolated cluster bounding box.
            geo_bounds: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
            raster_shape: (height, width) of the parent raster.

        Returns:
            Tuple of (classification_string, confidence_float, geojson_polygon_dict).
        """
        min_lon, min_lat, max_lon, max_lat = geo_bounds
        h, w = raster_shape
        lon_step = (max_lon - min_lon) / w
        lat_step = (max_lat - min_lat) / h

        min_r, min_c, max_r, max_c = bbox.pixel_bbox
        box_w = max_c - min_c + 1
        box_h = max_r - min_r + 1
        aspect_ratio = max(box_w, box_h) / max(min(box_w, box_h), 1)

        # 1. Simulate YOLOv8-OBB Classification based on geometry footprint
        if aspect_ratio > 3.5 and bbox.pixel_count > 150:
            classification = "Airfield_Runway"
            confidence = 0.965
        elif aspect_ratio < 1.3 and bbox.pixel_count < 100:
            classification = "Radar_Dome"
            confidence = 0.942
        elif 1.4 <= aspect_ratio <= 3.0 and bbox.pixel_count > 120:
            classification = "Logistics_Depot"
            confidence = 0.915
        elif aspect_ratio < 1.4 and 100 <= bbox.pixel_count <= 250:
            classification = "Fuel_Storage_Tank"
            confidence = 0.890
        else:
            classification = "Unknown_Structure"
            confidence = 0.820

        # 2. Simulate GeoSAM Zero-Shot Perimeter Extraction
        # Traces the physical boundary vertices around the centroid
        cr, cc = bbox.pixel_centroid
        hr = box_h / 2.0
        wc = box_w / 2.0

        # Octagonal perimeter trace
        pixel_points = [
            (cr - hr, cc - 0.7 * wc),
            (cr - hr, cc + 0.7 * wc),
            (cr - 0.7 * hr, cc + wc),
            (cr + 0.7 * hr, cc + wc),
            (cr + hr, cc + 0.7 * wc),
            (cr + hr, cc - 0.7 * wc),
            (cr + 0.7 * hr, cc - wc),
            (cr - 0.7 * hr, cc - wc),
            (cr - hr, cc - 0.7 * wc)  # Close ring
        ]

        # Convert to WGS 84 (EPSG:4326)
        geo_ring = []
        for r_p, c_p in pixel_points:
            lon = min_lon + (c_p * lon_step)
            lat = max_lat - (r_p * lat_step)
            geo_ring.append([round(float(lon), 6), round(float(lat), 6)])

        polygon = shapely.geometry.Polygon(geo_ring)
        if not polygon.is_valid:
            polygon = make_valid(polygon)

        geojson_geom = shapely.geometry.mapping(polygon)
        return classification, confidence, geojson_geom

    def process_and_store(
        self,
        binary_mask: np.ndarray,
        geo_bounds: List[float],
        detection_date: str,
        source_metadata: Dict
    ) -> List[VectorizedDetection]:
        """Execute full vectorization and database insertion workflow."""
        bboxes = self.isolate_bounding_boxes(binary_mask)
        detections: List[VectorizedDetection] = []

        for bbox in bboxes:
            classification, confidence, geojson_geom = self.simulate_yolo_and_geosam(
                bbox=bbox,
                geo_bounds=geo_bounds,
                raster_shape=binary_mask.shape
            )

            rec = VectorizedDetection(
                geometry_geojson=geojson_geom,
                classification=classification,
                confidence=confidence,
                detection_date=detection_date,
                source_imagery=source_metadata
            )
            detections.append(rec)

        saved_count = self.db_writer.insert_batch(detections)
        logger.info(
            "Vectorization and storage complete",
            generated=len(detections),
            saved_to_db=saved_count
        )
        return detections


@click.command()
@click.option("--test", is_flag=True, default=False, help="Run test vectorization with synthetic mask.")
@click.option("--dry-run", is_flag=True, default=False, help="Skip live database writes.")
def main(test: bool, dry_run: bool):
    """Caelum-EO Vectorization & Storage CLI."""
    writer = PostGISWriter(dry_run=dry_run)
    pipeline = VectorizationPipeline(db_writer=writer)

    if test:
        # Create synthetic 256x256 binary mask with 2 distinct clusters
        mask = np.zeros((256, 256), dtype=np.uint8)
        # Cluster 1: Logistics Depot (rectangular)
        mask[40:70, 40:100] = 1
        # Cluster 2: Radar Dome (compact circular/square)
        mask[160:190, 160:190] = 1

        geo_bounds = [22.8, 53.8, 24.5, 54.7]
        now_iso = datetime.now(timezone.utc).isoformat()
        src_meta = {"item_id": "S2A_TEST_SYNTHETIC", "platform": "sentinel-2a"}

        results = pipeline.process_and_store(mask, geo_bounds, now_iso, src_meta)
        print(f"Pipeline executed successfully! Vectorized {len(results)} targets:")
        for r in results:
            print(f" - [{r.classification}] Conf: {r.confidence*100:.1f}%, ID: {r.id}")


if __name__ == "__main__":
    main()
