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


# ============================================================================
# Version 5 Models: Multi-Modal Telemetry, Dark-Target Correlation & Network RL
# ============================================================================


class VesselTrackResponse(BaseModel):
    """AIS vessel position record."""

    id: str
    mmsi: str
    vessel_name: Optional[str] = None
    vessel_type: Optional[str] = None
    flag: Optional[str] = None
    timestamp: str
    lon: float
    lat: float
    speed_knots: Optional[float] = None
    course_deg: Optional[float] = None
    navigational_status: Optional[str] = None
    is_dark: bool
    dark_near_infra_km: Optional[float] = None
    ingested_at: str


class AircraftTrackResponse(BaseModel):
    """ADS-B aircraft position record."""

    id: str
    icao24: str
    callsign: Optional[str] = None
    country_of_origin: Optional[str] = None
    aircraft_category: Optional[str] = None
    timestamp: str
    lon: float
    lat: float
    altitude_baro_m: Optional[float] = None
    speed_ms: Optional[float] = None
    is_on_ground: bool
    is_dark: bool
    dark_near_infra_km: Optional[float] = None
    ingested_at: str


class DarkTargetEventResponse(BaseModel):
    """Correlated dark-transponder event near a known EO detection."""

    id: str
    event_type: str  # "AIS" | "ADSB"
    entity_id: str
    entity_name: Optional[str] = None
    detection_id: str
    dark_start: str
    dark_end: Optional[str] = None
    duration_minutes: Optional[int] = None
    closest_approach_km: float
    threat_score: float
    analyst_reviewed: bool
    analyst_notes: Optional[str] = None
    created_at: str


class TelemetryIngestRequest(BaseModel):
    """Request payload for triggering a local telemetry directory ingest."""

    directory_path: str = Field(..., description="Absolute path to the local telemetry dump directory")
    dry_run: bool = Field(False, description="If true, parse and validate files without DB insert")


class TelemetryIngestResponse(BaseModel):
    """Summary statistics for a completed telemetry ingest run."""

    vessel_rows_parsed: int
    vessel_rows_inserted: int
    aircraft_rows_parsed: int
    aircraft_rows_inserted: int
    dark_events_detected: int
    dark_events_inserted: int
    errors: List[str]


class NetworkAnalysisRequest(BaseModel):
    """Request to trigger full logistics network analysis + RL training."""

    snapshot_label: Optional[str] = Field(None, description="Human-readable label for this snapshot")
    n_episodes: int = Field(500, ge=10, le=5000, description="RL training episode count")


class NetworkAnalysisResponse(BaseModel):
    """Result of a logistics network graph analysis and RL run."""

    node_count: int
    edge_count: int
    critical_node_ids: List[str]
    predicted_expansion_ids: List[str]
    centrality_scores: Dict[str, float]
    threat_flow_scores: Dict[str, float]
    computed_at: str


class NetworkSnapshotResponse(BaseModel):
    """Persisted logistics network graph snapshot."""

    id: str
    snapshot_label: str
    computation_timestamp: str
    node_count: int
    edge_count: int
    critical_node_ids: List[str]
    predicted_expansion_ids: List[str]
    rl_episode_rewards: Optional[List[float]] = None
    created_at: str
