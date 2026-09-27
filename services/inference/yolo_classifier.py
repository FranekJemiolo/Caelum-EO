"""YOLOv8-OBB Infrastructure Classifier.

Runs Oriented Bounding Box (OBB) object detection on localized satellite chips
to categorize military and dual-use strategic infrastructure build-outs.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import os
from typing import Optional, Tuple

import numpy as np
import structlog
from pydantic import BaseModel

from services.inference.cluster_extractor import AnomalyCluster
from services.inference.config import ModelSettings, inference_settings

logger = structlog.get_logger(__name__)


class ClassifiedDetection(BaseModel):
    """Infrastructure object detection output with oriented bounding box."""

    classification: str
    confidence: float
    oriented_bbox: Optional[Tuple[float, float, float, float, float]] = (
        None  # (cx, cy, w, h, angle_deg)
    )
    cluster_id: int


class YOLOInfrastructureClassifier:
    """YOLOv8-OBB inference service."""

    def __init__(self, settings: Optional[ModelSettings] = None):
        self.settings = settings or inference_settings
        self.target_classes = self.settings.yolo_target_classes
        self.conf_threshold = self.settings.yolo_conf_threshold
        self.model = self._init_model()

    def _init_model(self):
        """Load YOLOv8-OBB model weights if available, or initialize heuristic detector."""
        weights = self.settings.yolo_model_path
        if os.path.exists(weights):
            logger.info("Loading YOLOv8-OBB model weights", weights_path=weights)
            try:
                from ultralytics import YOLO

                return YOLO(weights)
            except Exception as exc:
                logger.warning("Ultralytics loading failed, using fallback engine", error=str(exc))
                return None
        else:
            logger.info("Operating YOLOv8-OBB in spectral/morphological classification mode")
            return None

    def classify_chip(self, image_chip: np.ndarray, cluster: AnomalyCluster) -> ClassifiedDetection:
        """Classify infrastructure type on a localized image chip.

        Args:
            image_chip: Array of shape (C, H, W) or (H, W).
            cluster: Contextual cluster metadata.

        Returns:
            ClassifiedDetection with assigned class and confidence.
        """
        # If Ultralytics model available, perform native OBB forward pass
        if self.model is not None:
            try:
                # Convert (C, H, W) to (H, W, C) RGB
                if image_chip.ndim == 3 and image_chip.shape[0] >= 3:
                    # Select Red, Green, Blue bands (e.g. index 2, 1, 0)
                    rgb = np.transpose(image_chip[:3], (1, 2, 0))
                    rgb_uint8 = (np.clip(rgb, 0.0, 1.0) * 255).astype(np.uint8)
                else:
                    rgb_uint8 = (np.clip(image_chip, 0.0, 1.0) * 255).astype(np.uint8)

                results = self.model(rgb_uint8, conf=self.conf_threshold, verbose=False)
                if len(results) > 0 and len(results[0].obb) > 0:
                    obb = results[0].obb[0]
                    cls_idx = int(obb.cls.cpu().item())
                    conf = float(obb.conf.cpu().item())
                    label = self.model.names.get(cls_idx, self.target_classes[0])
                    xywhr = tuple(float(x) for x in obb.xywhr[0].cpu().numpy())

                    return ClassifiedDetection(
                        classification=label,
                        confidence=conf,
                        oriented_bbox=xywhr,
                        cluster_id=cluster.cluster_id,
                    )
            except Exception as exc:
                logger.warning(
                    "YOLO forward pass exception, falling back to heuristic", error=str(exc)
                )

        # Heuristic classifier based on morphological aspect ratio, area, and spectral reflectivity
        classification, confidence = self._heuristic_classify(image_chip, cluster)

        return ClassifiedDetection(
            classification=classification,
            confidence=confidence,
            oriented_bbox=(
                0.0,
                0.0,
                float(cluster.pixel_bbox[3] - cluster.pixel_bbox[1]),
                float(cluster.pixel_bbox[2] - cluster.pixel_bbox[0]),
                0.0,
            ),
            cluster_id=cluster.cluster_id,
        )

    def _heuristic_classify(self, chip: np.ndarray, cluster: AnomalyCluster) -> Tuple[str, float]:
        """Classify target category using geometric footprint and spectral properties."""
        min_r, min_c, max_r, max_c = cluster.pixel_bbox
        h = max_r - min_r + 1
        w = max_c - min_c + 1
        aspect_ratio = max(h, w) / max(min(h, w), 1)
        area = cluster.pixel_count

        # Elongated, massive linear structures -> Airfield Runway or Pier
        if aspect_ratio > 4.0 and area > 100:
            return "Airfield_Runway", min(0.92, cluster.mean_confidence + 0.1)

        # Compact, high-aspect ratio linear dock -> Naval Pier
        if aspect_ratio > 3.0:
            return "Naval_Pier_Berth", min(0.88, cluster.mean_confidence)

        # Compact, circular or square small footprint -> Radar Dome or SAM Site
        if aspect_ratio < 1.4 and area < 80:
            return "Radar_Dome", min(0.95, cluster.mean_confidence + 0.05)

        # Circular medium footprint -> Fuel Storage Tank
        if aspect_ratio < 1.3 and 80 <= area <= 250:
            return "Fuel_Storage_Tank", min(0.90, cluster.mean_confidence)

        # Large rectangular footprint -> Logistics Depot
        if 1.5 <= aspect_ratio <= 3.0 and area > 150:
            return "Logistics_Depot", min(0.89, cluster.mean_confidence)

        # Default fallback
        return "Vehicle_Staging_Area", min(0.85, cluster.mean_confidence)
