"""Machine Learning Inference Package for Project Caelum-EO."""

from services.inference.config import ModelSettings, inference_settings

try:
    from services.inference.cluster_extractor import AnomalyCluster, SpatialClusterExtractor
    from services.inference.geosam_vectorizer import GeoSAMVectorizer
    from services.inference.pipeline import GEOINTInferencePipeline, InfrastructureDetectionRecord
    from services.inference.prithvi_detector import PrithviChangeDetector
    from services.inference.yolo_classifier import ClassifiedDetection, YOLOInfrastructureClassifier

    __all__ = [
        "ModelSettings",
        "inference_settings",
        "PrithviChangeDetector",
        "SpatialClusterExtractor",
        "AnomalyCluster",
        "YOLOInfrastructureClassifier",
        "ClassifiedDetection",
        "GeoSAMVectorizer",
        "GEOINTInferencePipeline",
        "InfrastructureDetectionRecord",
    ]
except ImportError:
    __all__ = [
        "ModelSettings",
        "inference_settings",
    ]

