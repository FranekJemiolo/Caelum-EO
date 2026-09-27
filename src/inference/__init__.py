"""Inference pipeline package for Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)."""

from src.inference.detector import InferenceCoordinator
from src.inference.multimodal_detector import CrossAttentionFusionHead, MultiModalChangeDetector
from src.inference.prithvi_detector import PrithviChangeDetector
from src.inference.vectorizer import VectorizationEngine
from src.inference.yolo_classifier import YOLOInfrastructureClassifier

__all__ = [
    "InferenceCoordinator",
    "PrithviChangeDetector",
    "MultiModalChangeDetector",
    "CrossAttentionFusionHead",
    "VectorizationEngine",
    "YOLOInfrastructureClassifier",
]
