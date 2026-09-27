"""YOLOv8 Infrastructure Classifier.

Categorizes detected change clusters into tactical infrastructure categories
matching the PostGIS infrastructure_class enum:
- LOGISTICS_DEPOT
- RUNWAY_TAXIWAY
- RADAR_DOME
- DEFENSE_REVETMENT
- INDUSTRIAL_BUILDING
- UNKNOWN_STRUCTURE

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import os
from typing import Tuple

import numpy as np
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

VALID_CLASSES = [
    "LOGISTICS_DEPOT",
    "RUNWAY_TAXIWAY",
    "RADAR_DOME",
    "DEFENSE_REVETMENT",
    "INDUSTRIAL_BUILDING",
    "UNKNOWN_STRUCTURE",
]


class ClassificationResult(BaseModel):
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (min_r, min_c, max_r, max_c)
    aspect_ratio: float
    area_pixels: int


class YOLOInfrastructureClassifier:
    """Classifies localized imagery chips into tactical target categories."""

    def __init__(
        self, weights_path: str = "weights/yolov8_obb_geoint.pt", conf_threshold: float = 0.50
    ):
        self.weights_path = weights_path
        self.conf_threshold = conf_threshold
        self.model = self._load_yolo()

    def _load_yolo(self):
        """Attempt to load Ultralytics YOLO model, fallback to morphological classifier."""
        if os.path.exists(self.weights_path):
            try:
                from ultralytics import YOLO

                logger.info("Loading YOLOv8 weights checkpoint", weights=self.weights_path)
                return YOLO(self.weights_path)
            except Exception as exc:
                logger.warning(
                    "Failed loading Ultralytics YOLO; using morphological classifier",
                    error=str(exc),
                )
        return None

    def classify_cluster(
        self,
        chip: np.ndarray,
        bbox: Tuple[int, int, int, int],
        pixel_count: int,
        mean_anomaly_prob: float = 0.85,
    ) -> ClassificationResult:
        """Classify infrastructure from image chip and spatial geometry."""
        min_r, min_c, max_r, max_c = bbox
        h = max_r - min_r + 1
        w = max_c - min_c + 1
        aspect_ratio = max(w, h) / max(min(w, h), 1)

        # 1. If native YOLO model weights present, run inference
        if self.model is not None:
            try:
                # Transpose to RGB uint8
                rgb = (np.clip(chip[:3], 0.0, 1.0).transpose((1, 2, 0)) * 255).astype(np.uint8)
                preds = self.model(rgb, conf=self.conf_threshold, verbose=False)
                if len(preds) > 0 and len(preds[0].boxes) > 0:
                    top_box = preds[0].boxes[0]
                    cls_id = int(top_box.cls.item())
                    conf = float(top_box.conf.item())
                    label = self.model.names.get(cls_id, "UNKNOWN_STRUCTURE")
                    if label in VALID_CLASSES:
                        return ClassificationResult(
                            label=label,
                            confidence=round(conf, 4),
                            bbox=bbox,
                            aspect_ratio=round(aspect_ratio, 2),
                            area_pixels=pixel_count,
                        )
            except Exception as exc:
                logger.debug(
                    "YOLO forward pass exception, using morphological rules", error=str(exc)
                )

        # 2. Heuristic morphological classifier (deterministic and robust)
        # Elongated, high-pixel count -> Runway or Taxiway
        if aspect_ratio >= 3.5 and pixel_count >= 120:
            label = "RUNWAY_TAXIWAY"
            confidence = min(0.97, mean_anomaly_prob + 0.1)
        # Compact, circular or square small footprint -> Radar Dome
        elif aspect_ratio < 1.35 and pixel_count < 90:
            label = "RADAR_DOME"
            confidence = min(0.95, mean_anomaly_prob + 0.08)
        # Rectangular large footprint -> Logistics Depot
        elif 1.4 <= aspect_ratio <= 3.2 and pixel_count >= 100:
            label = "LOGISTICS_DEPOT"
            confidence = min(0.92, mean_anomaly_prob + 0.05)
        # Medium footprint, moderate aspect ratio -> Industrial Building
        elif 1.2 <= aspect_ratio <= 2.2 and 50 <= pixel_count < 100:
            label = "INDUSTRIAL_BUILDING"
            confidence = min(0.88, mean_anomaly_prob)
        # Low aspect ratio, revetted perimeter -> Defense Revetment
        elif aspect_ratio < 1.6 and pixel_count > 150:
            label = "DEFENSE_REVETMENT"
            confidence = min(0.89, mean_anomaly_prob)
        else:
            label = "UNKNOWN_STRUCTURE"
            confidence = min(0.80, mean_anomaly_prob)

        return ClassificationResult(
            label=label,
            confidence=round(confidence, 4),
            bbox=bbox,
            aspect_ratio=round(aspect_ratio, 2),
            area_pixels=pixel_count,
        )
