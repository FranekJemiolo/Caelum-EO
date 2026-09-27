"""End-to-End GEOINT Machine Learning Inference Pipeline.

Orchestrates Stage 1 (Prithvi-EO-2.0 Change Detection) with Stage 2 (YOLOv8-OBB & GeoSAM)
to produce actionable PostGIS-ready vector intelligence records.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import structlog
from pydantic import BaseModel, Field

from services.inference.cluster_extractor import SpatialClusterExtractor
from services.inference.config import ModelSettings, inference_settings
from services.inference.geosam_vectorizer import GeoSAMVectorizer
from services.inference.prithvi_detector import PrithviChangeDetector
from services.inference.yolo_classifier import YOLOInfrastructureClassifier

logger = structlog.get_logger(__name__)


class InfrastructureDetectionRecord(BaseModel):
    """Normalized payload ready for PostGIS 'infrastructure_detections' table."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    geometry: Dict  # GeoJSON Polygon (EPSG:4326)
    classification: str
    confidence: float
    detection_date: str
    source_imagery: Dict


class GEOINTInferencePipeline:
    """Two-stage inference engine."""

    def __init__(self, settings: Optional[ModelSettings] = None):
        self.settings = settings or inference_settings
        self.prithvi = PrithviChangeDetector(self.settings)
        self.cluster_extractor = SpatialClusterExtractor(self.settings)
        self.yolo = YOLOInfrastructureClassifier(self.settings)
        self.geosam = GeoSAMVectorizer(self.settings)

    def process_scene_pair(
        self,
        temporal_stack: np.ndarray,
        geo_bounds: List[float],
        detection_date: Optional[str] = None,
        source_metadata: Optional[Dict] = None,
        threshold: Optional[float] = None,
    ) -> List[InfrastructureDetectionRecord]:
        """Run complete 2-stage inference over a multi-temporal satellite image pair.

        Args:
            temporal_stack: Array of shape (2, 6, H, W).
            geo_bounds: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
            detection_date: Timestamp of newly acquired image (ISO format).
            source_metadata: Raw STAC metadata dictionary.

        Returns:
            List of detected infrastructure records with GeoJSON geometry, classification,
            confidence score, and source metadata.
        """
        assert (
            temporal_stack.ndim == 4 and temporal_stack.shape[0] == 2
        ), "temporal_stack must have shape (2, 6, H, W)"

        date_str = detection_date or datetime.now(timezone.utc).isoformat()
        src_meta = source_metadata or {}
        height, width = temporal_stack.shape[2], temporal_stack.shape[3]

        logger.info(
            "Starting GEOINT pipeline inference",
            raster_shape=(height, width),
            geo_bounds=geo_bounds,
        )

        # Stage 1: Prithvi-EO Foundation Model Change Detection
        binary_mask, prob_map = self.prithvi.detect_changes(temporal_stack, threshold=threshold)

        # Stage 2: Cluster Extraction & Bounding Boxes
        clusters = self.cluster_extractor.extract_clusters(
            binary_mask=binary_mask, prob_map=prob_map, geo_bounds=geo_bounds
        )

        if not clusters:
            logger.info("No anomalous structural clusters detected above threshold")
            return []

        # T1 (Newly acquired) image for chip cropping
        t1_raster = temporal_stack[1]

        records: List[InfrastructureDetectionRecord] = []

        # Stage 3: Secondary Classification & High-Precision Vectorization
        for cluster in clusters:
            chip, offset = self.cluster_extractor.crop_image_chip(t1_raster, cluster)

            # Stage 3a: YOLOv8-OBB Object Detection
            classified = self.yolo.classify_chip(chip, cluster)

            # Stage 3b: GeoSAM Zero-Shot Perimeter Vectorization
            polygon_geojson = self.geosam.segment_and_vectorize(
                image_chip=chip,
                cluster=cluster,
                offset_row_col=offset,
                geo_bounds=geo_bounds,
                full_raster_shape=(height, width),
            )

            record = InfrastructureDetectionRecord(
                geometry=polygon_geojson,
                classification=classified.classification,
                confidence=round(classified.confidence, 4),
                detection_date=date_str,
                source_imagery=src_meta,
            )
            records.append(record)

        logger.info("GEOINT inference pipeline concluded", generated_detections=len(records))
        return records
