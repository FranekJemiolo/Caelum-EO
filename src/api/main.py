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
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image

from src.api.models import (
    ImageryResponse,
    ReviewPayload,
    ReviewResponse,
    ZoneSummary,
)
from src.api.service import triage_service

app = FastAPI(
    title="Project Caelum-EO GEOINT Triage API",
    description="Automated GEOINT Infrastructure Detection, Review, and Analytical API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Enable CORS for local and staging development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
def get_zones_summary() -> List[ZoneSummary]:
    """Retrieve aggregated detection metrics grouped by strategic surveillance zone."""
    return triage_service.get_zones_summary()


@app.get("/api/v1/triage/queue")
def get_triage_queue(
    limit: int = Query(50, ge=1, le=200, description="Max triage queue items to return"),
) -> List[Dict[str, Any]]:
    """Retrieve pending review detections ranked by descending priority score."""
    return triage_service.get_triage_queue(limit=limit)


@app.get("/api/v1/detections/{detection_id}/imagery", response_model=ImageryResponse)
def get_detection_imagery(detection_id: str) -> ImageryResponse:
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
def get_detection_chip_image(detection_id: str, layer_type: str) -> Response:
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
) -> ReviewResponse:
    """Submit Human-in-the-Loop review, update classification, and log audit trail."""
    result = triage_service.submit_review(detection_id=detection_id, payload=payload)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection with ID '{detection_id}' not found.",
        )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
