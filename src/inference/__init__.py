"""Inference pipeline package for Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO).

Heavy ML dependencies (torch, torchvision) are optional.  They are only required
when actually running inference; tests that do not exercise the GPU path will
still import successfully without them.
"""

from __future__ import annotations

__all__ = [
    "InferenceCoordinator",
    "PrithviChangeDetector",
    "MultiModalChangeDetector",
    "CrossAttentionFusionHead",
    "VectorizationEngine",
    "YOLOInfrastructureClassifier",
]


def __getattr__(name: str):  # noqa: ANN001
    """Lazy-load heavy submodules only when first accessed."""
    _map = {
        "InferenceCoordinator": ("src.inference.detector", "InferenceCoordinator"),
        "PrithviChangeDetector": ("src.inference.prithvi_detector", "PrithviChangeDetector"),
        "MultiModalChangeDetector": (
            "src.inference.multimodal_detector",
            "MultiModalChangeDetector",
        ),
        "CrossAttentionFusionHead": (
            "src.inference.multimodal_detector",
            "CrossAttentionFusionHead",
        ),
        "VectorizationEngine": ("src.inference.vectorizer", "VectorizationEngine"),
        "YOLOInfrastructureClassifier": (
            "src.inference.yolo_classifier",
            "YOLOInfrastructureClassifier",
        ),
    }
    if name in _map:
        module_path, attr = _map[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr)
    raise AttributeError(f"module 'src.inference' has no attribute {name!r}")
