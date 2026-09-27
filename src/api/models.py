"""Pydantic Models and Enums for Caelum-EO Triage & Analytical APIs."""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class InfrastructureClass(str, Enum):
    LOGISTICS_DEPOT = "LOGISTICS_DEPOT"
    RUNWAY_TAXIWAY = "RUNWAY_TAXIWAY"
    RADAR_DOME = "RADAR_DOME"
    DEFENSE_REVETMENT = "DEFENSE_REVETMENT"
    INDUSTRIAL_BUILDING = "INDUSTRIAL_BUILDING"
    UNKNOWN_STRUCTURE = "UNKNOWN_STRUCTURE"


class ReviewStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    VERIFIED = "VERIFIED"
    MISCLASSIFIED = "MISCLASSIFIED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class ReviewPayload(BaseModel):
    """Payload submitted during Human-in-the-Loop reclassification and triage."""

    review_status: ReviewStatus
    verified_class: Optional[InfrastructureClass] = None
    reviewer_notes: Optional[str] = Field(None, max_length=2000)
    reviewed_by: Optional[str] = Field(None, max_length=128)


class ReviewResponse(BaseModel):
    id: str
    review_status: ReviewStatus
    verified_class: Optional[InfrastructureClass] = None
    priority_score: float
    reviewer_notes: Optional[str] = None
    reviewed_by: str
    reviewed_at: str
    message: str


class ZoneSummary(BaseModel):
    """Aggregated geospatial metrics for strategic surveillance zones."""

    id: str
    name: str
    alert_level: str
    boundary: Dict[str, Any]
    total_detections: int
    new_detections_24h: int
    new_detections_7d: int
    high_priority_count: int
    classification_breakdown: Dict[str, int]


class ImageryResponse(BaseModel):
    """Satellite image chip references for multi-temporal inspection."""

    detection_id: str
    t0_image_url: str
    t1_image_url: str
    mask_image_url: str
    sensor_source: str
    baseline_timestamp: str
    detection_timestamp: str
    stac_metadata: Dict[str, Any] = {}
