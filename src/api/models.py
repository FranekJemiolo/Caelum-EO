"""Pydantic Models and Enums for Caelum-EO Triage & Analytical APIs."""

from enum import Enum
from typing import Any, Dict, List, Optional

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


# ============================================================================
# Version 3 Models: Configuration, Threaded Notes, Audit Log, Saved Filters
# ============================================================================


class SystemConfigItem(BaseModel):
    """Dynamic system configuration entry."""

    id: Optional[int] = None
    key: str
    value: str
    description: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None


class SystemConfigUpdate(BaseModel):
    """Payload for updating or creating dynamic system configuration."""

    value: str
    description: Optional[str] = None


class DetectionCommentCreate(BaseModel):
    """Payload for posting a threaded analyst note."""

    comment: str = Field(..., min_length=1, max_length=5000)


class DetectionCommentResponse(BaseModel):
    """Analyst comment response."""

    id: str
    detection_id: str
    user_id: Optional[str] = None
    username: str
    comment: str
    created_at: str


class DetectionAuditResponse(BaseModel):
    """Lifecycle audit log entry for detection transitions."""

    id: str
    detection_id: str
    previous_state: Optional[str] = None
    new_state: str
    user_id: Optional[str] = None
    username: str
    note: Optional[str] = None
    timestamp: str


class SavedFilterCreate(BaseModel):
    """Payload for saving an analyst filter preset."""

    name: str = Field(..., min_length=1, max_length=128)
    filter_json: Dict[str, Any]


class SavedFilterResponse(BaseModel):
    """Saved analyst filter view."""

    id: str
    user_id: str
    name: str
    filter_json: Dict[str, Any]
    created_at: str


class ExportRequest(BaseModel):
    """Parameters for exporting intelligence detections."""

    detection_ids: Optional[List[str]] = None
    zone_id: Optional[str] = None
    format: str = Field("geojson", pattern="^(geojson|csv)$")


class ViewshedRequest(BaseModel):
    """Request payload for radar viewshed and line-of-sight calculations."""

    detection_id: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    observer_height: float = 15.0
    target_height: float = 2.0
    max_radius_km: float = 12.0


class ViewshedResponse(BaseModel):
    """GeoJSON Feature response containing viewshed polygon."""

    type: str = "Feature"
    geometry: Dict[str, Any]
    properties: Dict[str, Any]


class SitrepGenerateRequest(BaseModel):
    """Parameters for generating a local LLM SITREP."""

    hours_lookback: int = Field(24, ge=1, le=720)
    model: str = "llama3:8b-instruct"
    title: Optional[str] = None
    zone_id: Optional[str] = None


class SitrepResponse(BaseModel):
    """Generated daily military SITREP brief."""

    id: str
    title: str
    time_window_start: str
    time_window_end: str
    model_name: str
    sitrep_content: str
    target_count: int
    high_priority_count: int
    status: str
    created_at: str


class VelocityPoint(BaseModel):
    """Historical area footprint data point for a class."""

    timestamp: str
    cumulative_area_sq_m: float
    expansion_rate_sq_m_per_day: float


class VelocityClassMetrics(BaseModel):
    """Construction velocity metrics for a specific infrastructure class."""

    classification: str
    current_area_sq_m: float
    expansion_rate_sq_m_per_day: float
    total_detections: int
    timeline: List[VelocityPoint]


class VelocityResponse(BaseModel):
    """Area construction velocity and Pattern of Life analytics."""

    zone_id: Optional[str] = None
    total_area_sq_m: float
    mean_velocity_sq_m_per_day: float
    classes: List[VelocityClassMetrics]


class CoTBroadcastResponse(BaseModel):
    """Result of Cursor-on-Target (CoT) tactical edge dispatch."""

    status: str
    detection_id: str
    uid: str
    callsign: str
    mil_std_2525_type: str
    target_host: str
    target_port: int
    protocol: str
    xml_payload: str
    timestamp: str
