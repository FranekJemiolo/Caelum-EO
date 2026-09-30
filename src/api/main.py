"""FastAPI Application for Project Caelum-EO GEOINT Platform.

Provides REST and GeoJSON endpoints for:
- Vector Detection Exploration
- Strategic Zone Geospatial Aggregations
- High-Priority Triage Queue
- Multi-Temporal Satellite Chip Retrieval
- Human-in-the-Loop (HITL) Reclassification & Review

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import io
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image

from src.analytics.network_graph import network_engine
from src.api.auth import User, get_current_user, require_roles
from src.api.auth import router as auth_router
from src.api.cot_dispatcher import cot_dispatcher
from src.api.models import (
    AircraftTrackResponse,
    CoTBroadcastResponse,
    DarkTargetEventResponse,
    DetectionAuditResponse,
    DetectionCommentCreate,
    DetectionCommentResponse,
    ExportRequest,
    ImageryResponse,
    NetworkAnalysisRequest,
    NetworkAnalysisResponse,
    NetworkSnapshotResponse,
    ReviewPayload,
    ReviewResponse,
    SavedFilterCreate,
    SavedFilterResponse,
    SitrepGenerateRequest,
    SitrepResponse,
    SystemConfigItem,
    SystemConfigUpdate,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    VelocityResponse,
    VesselTrackResponse,
    ViewshedRequest,
    ViewshedResponse,
    ZoneSummary,
)
from src.api.service import triage_service
from src.api.sitrep_generator import sitrep_generator
from src.api.velocity import velocity_engine
from src.etl.telemetry_ingest import telemetry_ingestor
from src.ops import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    dlq_manager,
    generate_metrics_payload,
)

app = FastAPI(
    title="Project Caelum-EO GEOINT Triage API",
    description="Automated GEOINT Infrastructure Detection, Review, and Analytical API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.include_router(auth_router)

# Enable CORS for local and staging development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start_time
    path = request.url.path
    if path.startswith("/api/v1/detections/"):
        path = "/api/v1/detections/[id]"
    HTTP_REQUESTS_TOTAL.labels(
        method=request.method, endpoint=path, status=str(response.status_code)
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, endpoint=path).observe(duration)
    return response


@app.get("/api/v1/health")
def health_check() -> Dict[str, str]:
    """Liveness probe and system metadata."""
    return {
        "status": "healthy",
        "service": "caelum-eo-api",
        "repository": "github.com/FranekJemiolo/Caelum-EO",
        "version": "1.0.0",
    }


@app.get("/api/v1/detections")
def get_detections(
    classification: Optional[str] = Query(None, description="Infrastructure class filter"),
    review_status: Optional[str] = Query(None, description="Review status filter"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    start_date: Optional[str] = Query(None, description="Start ISO datetime"),
    end_date: Optional[str] = Query(None, description="End ISO datetime"),
    zone_id: Optional[str] = Query(None, description="Zone identifier"),
    limit: int = Query(100, ge=1, le=1000, description="Max features to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve detected infrastructure vectors formatted as GeoJSON FeatureCollection."""
    return triage_service.get_detections(
        classification=classification,
        review_status=review_status,
        min_confidence=min_confidence,
        start_date=start_date,
        end_date=end_date,
        zone_id=zone_id,
        limit=limit,
        offset=offset,
    )


@app.get("/api/v1/zones/summary", response_model=List[ZoneSummary])
def get_zones_summary(current_user: User = Depends(get_current_user)) -> List[ZoneSummary]:
    """Retrieve aggregated detection metrics grouped by strategic surveillance zone."""
    return triage_service.get_zones_summary()


@app.get("/api/v1/triage/queue")
def get_triage_queue(
    limit: int = Query(50, ge=1, le=200, description="Max triage queue items to return"),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve pending review detections ranked by descending priority score."""
    return triage_service.get_triage_queue(limit=limit)


@app.get("/api/v1/detections/{detection_id}/imagery", response_model=ImageryResponse)
def get_detection_imagery(
    detection_id: str,
    current_user: User = Depends(get_current_user),
) -> ImageryResponse:
    """Retrieve satellite image chip references and sensor metadata for inspection."""
    detection = triage_service.get_detection_by_id(detection_id)
    if not detection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection with ID '{detection_id}' not found.",
        )

    return ImageryResponse(
        detection_id=detection_id,
        t0_image_url=f"/api/v1/detections/{detection_id}/imagery/t0",
        t1_image_url=f"/api/v1/detections/{detection_id}/imagery/t1",
        mask_image_url=f"/api/v1/detections/{detection_id}/imagery/mask",
        sensor_source=detection.get("sensor_source", "Sentinel-2A-MSI-L2A"),
        baseline_timestamp=str(detection.get("baseline_timestamp")),
        detection_timestamp=str(detection.get("detection_timestamp")),
        stac_metadata=detection.get("stac_metadata", {}),
    )


@app.get("/api/v1/detections/{detection_id}/imagery/{layer_type}")
def get_detection_chip_image(
    detection_id: str,
    layer_type: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream binary PNG image chip for t0 baseline, t1 monitor, or difference mask."""
    if layer_type not in ["t0", "t1", "mask"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="layer_type must be one of ['t0', 't1', 'mask']",
        )

    # Check local disk
    prefix = detection_id[:8]
    disk_path = Path(f"data/chips/{prefix}/{layer_type}.png")
    if disk_path.exists():
        return FileResponse(disk_path, media_type="image/png")

    # Generate deterministic fallback visual chip
    np.random.seed(abs(hash(detection_id + layer_type)) % 10000)
    size = (128, 128)
    if layer_type == "t0":
        # Greenish terrain baseline
        img_arr = np.random.normal(100, 20, (size[0], size[1], 3)).clip(50, 180).astype(np.uint8)
        img_arr[..., 0] = (img_arr[..., 0] * 0.7).astype(np.uint8)  # Less red
        img_arr[..., 2] = (img_arr[..., 2] * 0.7).astype(np.uint8)  # Less blue
    elif layer_type == "t1":
        # Terrain with rectangular bright structural anomaly in center
        img_arr = np.random.normal(100, 20, (size[0], size[1], 3)).clip(50, 180).astype(np.uint8)
        img_arr[..., 0] = (img_arr[..., 0] * 0.7).astype(np.uint8)
        img_arr[..., 2] = (img_arr[..., 2] * 0.7).astype(np.uint8)
        img_arr[40:88, 40:88] = [210, 215, 220]  # Concrete tarmac / structure
    else:
        # Mask: Cyan overlay box
        img_arr = np.zeros((size[0], size[1], 4), dtype=np.uint8)
        img_arr[40:88, 40:88] = [0, 242, 254, 220]

    buf = io.BytesIO()
    mode = "RGBA" if layer_type == "mask" else "RGB"
    Image.fromarray(img_arr, mode=mode).save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.patch(
    "/api/v1/detections/{detection_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_200_OK,
)
def patch_detection_review(
    detection_id: str,
    payload: ReviewPayload,
    current_user: User = Depends(require_roles(["analyst", "admin"])),
) -> ReviewResponse:
    """Submit Human-in-the-Loop review, update classification, and log audit trail."""
    if not payload.reviewed_by or payload.reviewed_by == "Analyst":
        payload.reviewed_by = current_user.username
    result = triage_service.submit_review(detection_id=detection_id, payload=payload)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection with ID '{detection_id}' not found.",
        )
    return result


# ============================================================================
# Version Two Endpoints: Multi-Modal, MVT Cache, Active Learning & Edge Sync
# ============================================================================


@app.get("/api/v1/multimodal/status")
def get_multimodal_status(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return status and configuration of multi-modal SAR + Optical fusion engine."""
    from src.etl.sar_ingest import MULTIMODAL_BANDS

    try:
        from src.inference.prithvi_detector import get_optimal_device

        optimal_device = str(get_optimal_device())
    except ModuleNotFoundError:
        optimal_device = "cpu"

    return {
        "status": "active",
        "modalities": ["Copernicus Sentinel-2 Optical L2A", "Sentinel-1 C-Band SAR"],
        "polarizations": ["VV", "VH"],
        "coherence_supported": True,
        "band_count": len(MULTIMODAL_BANDS),
        "bands": MULTIMODAL_BANDS,
        "fusion_architecture": "Cross-Attention Dynamic Cloud-Gated Transformer",
        "optimal_device": optimal_device,
    }


@app.get("/api/v1/tiles/mvt/{z}/{x}/{y}")
def get_vector_tile(
    z: int,
    x: int,
    y: int,
    layer: str = Query("infrastructure_detections", description="Tile layer name"),
) -> Response:
    """Retrieve high-performance Mapbox Vector Tile (.pbf) with tier-1 caching."""
    from src.api.tile_cache import tile_cache

    cached = tile_cache.get_tile(layer, z, x, y)
    if cached is None:
        # Generate and cache tile
        cached = tile_cache.generate_synthetic_mvt(layer, z, x, y)
        tile_cache.set_tile(layer, z, x, y, cached)

    etag = tile_cache.compute_etag(cached)
    return Response(
        content=cached,
        media_type="application/x-protobuf",
        headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
            "Content-Type": "application/x-protobuf",
        },
    )


@app.get("/api/v1/mlops/active-learning/status")
def get_active_learning_status(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve active learning metrics, LoRA status, and FP suppression rate."""
    from dataclasses import asdict

    from src.mlops.active_learning import lora_worker

    return asdict(lora_worker.get_status())


@app.post("/api/v1/mlops/active-learning/trigger")
def trigger_active_learning_cycle(
    iteration_tag: str = Query("v2.1", description="Model iteration tag"),
    current_user: User = Depends(require_roles(["analyst", "admin"])),
) -> Dict[str, Any]:
    """Trigger automated LoRA fine-tuning cycle harvesting from review_audit_log."""
    from dataclasses import asdict

    from src.mlops.active_learning import harvest_engine, lora_worker

    audit_records = triage_service.get_audit_records(limit=200)
    manifest = harvest_engine.harvest_from_audit_records(audit_records)
    new_status = lora_worker.train_lora_iteration(manifest, iteration_tag=iteration_tag)
    return asdict(new_status)


@app.get("/api/v1/edge/sync/status")
def get_edge_sync_status(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve tactical edge delta synchronizer telemetry and pending queues."""
    from dataclasses import asdict

    from src.edge.sync import edge_sync

    return asdict(edge_sync.get_status())


@app.post("/api/v1/edge/sync/push")
def receive_edge_sync_batch(
    sync_bundle: Dict[str, Any],
    current_user: User = Depends(require_roles(["analyst", "admin"])),
) -> Dict[str, Any]:
    """Central HQ ingestion endpoint for receiving tactical edge sync bundles."""
    from src.edge.sync import edge_sync

    applied_deltas = edge_sync.receive_and_apply_batch(sync_bundle)
    return {
        "status": "success",
        "accepted_count": len(applied_deltas),
        "node_id": sync_bundle.get("node_id"),
    }


@app.get("/api/v1/citus/status")
def get_citus_status(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve Citus distributed spatial sharding status."""
    from src.db.citus_sharding import CitusShardingManager

    conn = triage_service.get_connection()
    return CitusShardingManager.check_sharding_status(conn)


# ============================================================================
# Version 3 Endpoints: Dynamic Config, Comments, Audit Logs, Saved Filters, Export
# ============================================================================


# --- 1. Dynamic Configuration API ---
@app.get("/api/v1/admin/config", response_model=List[SystemConfigItem])
def list_system_configurations(
    current_user: User = Depends(require_roles(["admin"])),
) -> List[Dict[str, Any]]:
    """Retrieve all dynamic system configurations (Admin only)."""
    return triage_service.get_configurations()


@app.get("/api/v1/admin/config/{key}", response_model=SystemConfigItem)
def get_system_configuration(
    key: str,
    current_user: User = Depends(require_roles(["admin"])),
) -> Dict[str, Any]:
    """Retrieve a specific dynamic system configuration by key (Admin only)."""
    config = triage_service.get_configuration(key)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration key '{key}' not found.",
        )
    return config


@app.put("/api/v1/admin/config/{key}", response_model=SystemConfigItem)
def update_system_configuration(
    key: str,
    payload: SystemConfigUpdate,
    current_user: User = Depends(require_roles(["admin"])),
) -> Dict[str, Any]:
    """Update or create a dynamic configuration entry (Admin only)."""
    return triage_service.set_configuration(
        key=key,
        value=payload.value,
        description=payload.description,
        user_id=current_user.id,
    )


@app.post("/api/v1/admin/config", response_model=SystemConfigItem)
def create_or_update_system_configuration(
    payload: SystemConfigItem,
    current_user: User = Depends(require_roles(["admin"])),
) -> Dict[str, Any]:
    """Create or update a dynamic configuration entry (Admin only)."""
    return triage_service.set_configuration(
        key=payload.key,
        value=payload.value,
        description=payload.description,
        user_id=current_user.id,
    )


# --- 2. Analyst Collaboration & Threaded Notes ---
@app.get(
    "/api/v1/detections/{detection_id}/comments",
    response_model=List[DetectionCommentResponse],
)
def get_detection_comments(
    detection_id: str,
    current_user: User = Depends(require_roles(["analyst", "admin"])),
) -> List[Dict[str, Any]]:
    """Retrieve threaded analyst comments for a specific detection."""
    return triage_service.get_comments(detection_id)


@app.post(
    "/api/v1/detections/{detection_id}/comments",
    response_model=DetectionCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_detection_comment(
    detection_id: str,
    payload: DetectionCommentCreate,
    current_user: User = Depends(require_roles(["analyst", "admin"])),
) -> Dict[str, Any]:
    """Post an analyst note to a detection thread."""
    return triage_service.add_comment(
        detection_id=detection_id,
        comment=payload.comment,
        username=current_user.username,
        user_id=current_user.id,
    )


# --- 3. Audit History Timeline ---
@app.get(
    "/api/v1/detections/{detection_id}/audit",
    response_model=List[DetectionAuditResponse],
)
def get_detection_audit_history(
    detection_id: str,
    current_user: User = Depends(require_roles(["analyst", "admin"])),
) -> List[Dict[str, Any]]:
    """Retrieve lifecycle state transition audit timeline for a detection."""
    return triage_service.get_detection_audit_trail(detection_id)


# --- 4. Saved Views & Advanced Filtering ---
@app.get("/api/v1/saved-filters", response_model=List[SavedFilterResponse])
def get_user_saved_filters(
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve personal saved filter presets for the authenticated user."""
    return triage_service.get_saved_filters(user_id=current_user.id)


@app.post(
    "/api/v1/saved-filters",
    response_model=SavedFilterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_saved_filter(
    payload: SavedFilterCreate,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Save a new filter preset for the authenticated user."""
    return triage_service.create_saved_filter(
        user_id=current_user.id,
        name=payload.name,
        filter_json=payload.filter_json,
    )


@app.delete("/api/v1/saved-filters/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_saved_filter(
    filter_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a saved filter preset."""
    triage_service.delete_saved_filter(user_id=current_user.id, filter_id=filter_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 5. Intelligence Export & Reporting Engine ---
@app.get("/api/v1/export")
def export_intelligence_data_get(
    format: str = Query("geojson", description="Export format: geojson or csv"),
    detection_ids: Optional[str] = Query(None, description="Comma-separated detection UUIDs"),
    zone_id: Optional[str] = Query(None, description="Strategic zone identifier"),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export intelligence detections to downloadable GeoJSON or CSV."""
    if format not in ["geojson", "csv"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="format must be either 'geojson' or 'csv'",
        )
    id_list = [i.strip() for i in detection_ids.split(",") if i.strip()] if detection_ids else None
    content, media_type, filename = triage_service.export_detections(
        detection_ids=id_list,
        zone_id=zone_id,
        format=format,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/v1/export")
def export_intelligence_data_post(
    payload: ExportRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export intelligence detections specified in request body."""
    content, media_type, filename = triage_service.export_detections(
        detection_ids=payload.detection_ids,
        zone_id=payload.zone_id,
        format=payload.format,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- 6. Observability & Fault Tolerance Endpoints ---
@app.get("/metrics")
def get_prometheus_metrics() -> Response:
    """Scrape endpoint for local Prometheus server."""
    payload, media_type = generate_metrics_payload()
    return Response(content=payload, media_type=media_type)


@app.get("/api/v1/ops/dlq")
def get_dead_letter_queue_messages(
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(require_roles(["admin", "analyst"])),
) -> List[Dict[str, Any]]:
    """Retrieve captured Dead Letter Queue failure events."""
    return dlq_manager.get_dlq_messages(limit=limit)


# --- 7. Version 4: 3D Terrain Viewshed Analytics ---
@app.post("/api/v1/analytics/viewshed", response_model=ViewshedResponse)
def compute_viewshed(
    payload: ViewshedRequest,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Calculate radar line-of-sight viewshed over 3D Digital Elevation Model (DEM)."""
    return triage_service.calculate_viewshed(
        detection_id=payload.detection_id,
        lon=payload.lon,
        lat=payload.lat,
        observer_height=payload.observer_height,
        target_height=payload.target_height,
        max_radius_km=payload.max_radius_km,
    )


@app.get("/api/v1/analytics/velocity", response_model=VelocityResponse)
def get_construction_velocity(
    zone_id: Optional[str] = Query(None, description="Optional zone ID filter"),
    months_lookback: int = Query(6, ge=1, le=24, description="Lookback window in months"),
    current_user: User = Depends(get_current_user),
) -> VelocityResponse:
    """Calculate physical infrastructure construction velocity and Pattern of Life metrics."""
    return velocity_engine.calculate_velocity_metrics(
        zone_id=zone_id,
        months_lookback=months_lookback,
    )


# --- 8. Version 4: Generative AI Daily SITREPs ---
@app.get("/api/v1/sitreps", response_model=List[SitrepResponse])
def list_sitreps(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve recent military situation reports (SITREPs)."""
    return sitrep_generator.list_sitreps(limit=limit)


@app.post("/api/v1/sitreps/generate", response_model=SitrepResponse)
def generate_sitrep(
    payload: SitrepGenerateRequest,
    current_user: User = Depends(require_roles(["admin", "analyst"])),
) -> Dict[str, Any]:
    """Generate a daily military situation report using local Ollama LLM."""
    return sitrep_generator.generate_sitrep(
        hours_lookback=payload.hours_lookback,
        model_name=payload.model,
        title=payload.title,
        zone_id=payload.zone_id,
    )


@app.get("/api/v1/sitreps/{report_id}", response_model=SitrepResponse)
def get_sitrep(
    report_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve detailed SITREP report by ID."""
    report = sitrep_generator.get_sitrep(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="SITREP report not found.")
    return report


@app.put("/api/v1/sitreps/{report_id}", response_model=SitrepResponse)
def update_sitrep(
    report_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_roles(["admin", "analyst"])),
) -> Dict[str, Any]:
    """Allow an analyst to edit and update a generated SITREP before final briefing."""
    content = payload.get("sitrep_content") or payload.get("content")
    if not content:
        raise HTTPException(
            status_code=400, detail="Field 'sitrep_content' or 'content' is required."
        )
    updated = sitrep_generator.update_sitrep(
        report_id=report_id,
        sitrep_content=content,
        title=payload.get("title"),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="SITREP report not found.")
    return updated


# --- 9. Version 4: Tactical Edge Cursor-on-Target (CoT) ATAK Dispatch ---
@app.post("/api/v1/cot/broadcast/{detection_id}", response_model=CoTBroadcastResponse)
def broadcast_cot(
    detection_id: str,
    current_user: User = Depends(require_roles(["admin", "analyst"])),
) -> Dict[str, Any]:
    """Broadcast a verified GEOINT detection as Cursor-on-Target (CoT) XML to ATAK network."""
    detection = triage_service.get_detection_by_id(detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="Detection not found.")

    res = cot_dispatcher.dispatch_detection(detection)
    return res


@app.get("/api/v1/cot/preview/{detection_id}")
def preview_cot(
    detection_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Preview standard Cursor-on-Target (CoT) XML payload without sending over network."""
    detection = triage_service.get_detection_by_id(detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="Detection not found.")

    xml_str, uid, cot_type, callsign = cot_dispatcher.serialize_cot_xml(detection)
    return Response(content=xml_str, media_type="application/xml")


# =============================================================================
# Version 5 Endpoints: Telemetry Ingest, Dark Events & Network Analysis
# =============================================================================


@app.post("/api/v1/telemetry/ingest", response_model=TelemetryIngestResponse)
def ingest_telemetry(
    payload: TelemetryIngestRequest,
    current_user: User = Depends(require_roles(["admin"])),
) -> TelemetryIngestResponse:
    """Trigger local AIS/ADS-B telemetry directory ingest and dark-target correlation.

    Scans the provided local directory for AIS CSV and ADS-B JSON/CSV files,
    bulk-inserts positions into PostGIS trajectory tables, and runs dark-event
    gap detection correlated against known EO infrastructure detections.
    """
    from pathlib import Path

    directory = Path(payload.directory_path)
    if not directory.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Directory not found: {payload.directory_path}",
        )

    if payload.dry_run:
        # Validate without DB writes by counting parseable records
        vessel_count = 0
        aircraft_count = 0
        from src.etl.telemetry_ingest import parse_adsb_json, parse_ais_csv

        for fp in sorted(directory.rglob("*")):
            name_lower = fp.stem.lower()
            suffix = fp.suffix.lower()
            if suffix == ".csv" and any(kw in name_lower for kw in ("ais", "vessel", "mmsi")):
                vessel_count += sum(1 for _ in parse_ais_csv(fp))
            elif suffix in (".json", ".ndjson") and any(
                kw in name_lower for kw in ("adsb", "aircraft", "flight")
            ):
                aircraft_count += sum(1 for _ in parse_adsb_json(fp))
        return TelemetryIngestResponse(
            vessel_rows_parsed=vessel_count,
            vessel_rows_inserted=0,
            aircraft_rows_parsed=aircraft_count,
            aircraft_rows_inserted=0,
            dark_events_detected=0,
            dark_events_inserted=0,
            errors=[],
        )

    stats = telemetry_ingestor.ingest_directory(directory)
    return TelemetryIngestResponse(
        vessel_rows_parsed=stats.vessel_rows_parsed,
        vessel_rows_inserted=stats.vessel_rows_inserted,
        aircraft_rows_parsed=stats.aircraft_rows_parsed,
        aircraft_rows_inserted=stats.aircraft_rows_inserted,
        dark_events_detected=stats.dark_events_detected,
        dark_events_inserted=stats.dark_events_inserted,
        errors=stats.errors[:50],  # Truncate error list
    )


@app.get("/api/v1/telemetry/vessels", response_model=List[VesselTrackResponse])
def get_vessel_tracks(
    mmsi: Optional[str] = Query(None, description="Filter by MMSI"),
    dark_only: bool = Query(False, description="Return only dark-event vessels"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
) -> List[VesselTrackResponse]:
    """Query AIS vessel tracks from the PostGIS trajectory table."""
    tracks = triage_service.get_vessel_tracks(
        mmsi=mmsi, dark_only=dark_only, limit=limit, offset=offset
    )
    return tracks


@app.get("/api/v1/telemetry/aircraft", response_model=List[AircraftTrackResponse])
def get_aircraft_tracks(
    icao24: Optional[str] = Query(None, description="Filter by ICAO24 hex"),
    dark_only: bool = Query(False, description="Return only dark-event aircraft"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
) -> List[AircraftTrackResponse]:
    """Query ADS-B aircraft tracks from the PostGIS trajectory table."""
    tracks = triage_service.get_aircraft_tracks(
        icao24=icao24, dark_only=dark_only, limit=limit, offset=offset
    )
    return tracks


@app.get("/api/v1/telemetry/dark-events", response_model=List[DarkTargetEventResponse])
def get_dark_events(
    event_type: Optional[str] = Query(None, description="'AIS' or 'ADSB'"),
    detection_id: Optional[str] = Query(None, description="Filter by EO detection UUID"),
    min_threat_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
) -> List[DarkTargetEventResponse]:
    """Retrieve dark-target correlation events sorted by threat score."""
    events = triage_service.get_dark_events(
        event_type=event_type,
        detection_id=detection_id,
        min_threat_score=min_threat_score,
        limit=limit,
        offset=offset,
    )
    return events


@app.post("/api/v1/network/analyse", response_model=NetworkAnalysisResponse)
def run_network_analysis(
    payload: NetworkAnalysisRequest = Body(default_factory=NetworkAnalysisRequest),
    current_user: User = Depends(require_roles(["admin", "analyst"])),
) -> NetworkAnalysisResponse:
    """Run full logistics network graph analysis with RL training.

    Builds a directed graph of infrastructure detections with telemetry flow edges,
    computes betweenness centrality for supply-chain critical node identification,
    trains a Stable Baselines3 PPO agent to predict future build-out expansions,
    and persists a graph snapshot to the database.
    """
    result = network_engine.run_full_analysis(
        snapshot_label=payload.snapshot_label,
        n_episodes=payload.n_episodes,
    )
    return NetworkAnalysisResponse(
        node_count=result.node_count,
        edge_count=result.edge_count,
        critical_node_ids=result.critical_node_ids,
        predicted_expansion_ids=result.predicted_expansion_ids,
        centrality_scores=result.centrality_scores,
        threat_flow_scores=result.threat_flow_scores,
        computed_at=result.computed_at,
    )


@app.get("/api/v1/network/graph")
def get_network_graph(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the current logistics network graph as D3 / Deck.gl node-link JSON."""
    return network_engine.get_graph_json()


@app.get("/api/v1/network/snapshots", response_model=List[NetworkSnapshotResponse])
def get_network_snapshots(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> List[NetworkSnapshotResponse]:
    """List persisted logistics network graph snapshots (most recent first)."""
    snapshots = triage_service.get_network_snapshots(limit=limit)
    return snapshots


@app.get("/api/v1/network/snapshots/latest", response_model=Optional[NetworkSnapshotResponse])
def get_latest_network_snapshot(
    current_user: User = Depends(get_current_user),
) -> Optional[NetworkSnapshotResponse]:
    """Retrieve the most recent persisted logistics network graph snapshot."""
    snap = network_engine.get_latest_snapshot()
    if snap is None:
        raise HTTPException(status_code=404, detail="No network snapshots found.")
    return NetworkSnapshotResponse(
        id=snap["id"],
        snapshot_label=snap["snapshot_label"],
        computation_timestamp=str(snap["computation_timestamp"]),
        node_count=snap["node_count"],
        edge_count=snap["edge_count"],
        critical_node_ids=snap["critical_node_ids"] or [],
        predicted_expansion_ids=snap["predicted_expansion_ids"] or [],
        rl_episode_rewards=snap.get("rl_episode_rewards"),
        created_at=str(snap["created_at"]),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
