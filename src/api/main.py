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
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image

from src.api.auth import User, get_current_user, require_roles
from src.api.auth import router as auth_router
from src.api.models import (
    DetectionAuditResponse,
    DetectionCommentCreate,
    DetectionCommentResponse,
    ExportRequest,
    ImageryResponse,
    ReviewPayload,
    ReviewResponse,
    SavedFilterCreate,
    SavedFilterResponse,
    SystemConfigItem,
    SystemConfigUpdate,
    ZoneSummary,
)
from src.api.service import triage_service
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
