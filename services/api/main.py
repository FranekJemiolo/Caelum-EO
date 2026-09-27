"""FastAPI Backend Server for Project Caelum-EO GEOINT Platform.

Exposes REST and GeoJSON endpoints consumed by the Deck.gl React frontend.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.database.db_client import PostGISDetectionRepository

app = FastAPI(
    title="Project Caelum-EO API",
    description="Automated GEOINT Infrastructure Detection API",
    version="0.1.0",
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = PostGISDetectionRepository()


class HealthResponse(BaseModel):
    status: str
    service: str
    repository: str


@app.get("/api/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy", service="caelum-eo-api", repository="github.com/FranekJemiolo/Caelum-EO"
    )


@app.get("/api/detections")
def get_detections(
    min_date: Optional[str] = Query(None, description="ISO timestamp for start of time window"),
    max_date: Optional[str] = Query(None, description="ISO timestamp for end of time window"),
    classes: Optional[str] = Query(None, description="Comma-separated classification tags"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
):
    """Retrieve detected infrastructure vectors formatted as GeoJSON FeatureCollection."""
    class_list = [c.strip() for c in classes.split(",")] if classes else None
    return repo.query_geojson_feature_collection(
        min_date=min_date, max_date=max_date, classes=class_list, min_confidence=min_confidence
    )


@app.get("/api/classes")
def get_classes() -> List[str]:
    """Retrieve distinct infrastructure classes."""
    return [
        "Logistics_Depot",
        "Radar_Dome",
        "Airfield_Runway",
        "SAM_Battery_Site",
        "Hardened_Shelter",
        "Naval_Pier_Berth",
        "Fuel_Storage_Tank",
        "Vehicle_Staging_Area",
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.api.main:app", host="0.0.0.0", port=8000, reload=True)
