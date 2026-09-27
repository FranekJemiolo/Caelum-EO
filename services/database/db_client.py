"""PostGIS Database Client for persisting and querying infrastructure detections.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import json
from typing import Dict, List, Optional
import structlog
from pydantic import BaseModel
from pydantic_settings import BaseSettings

logger = structlog.get_logger(__name__)


class DatabaseConfig(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "caelum_geoint"
    postgres_user: str = "caelum_user"
    postgres_password: str = "caelum_secure_password"


class PostGISDetectionRepository:
    """Manages spatial insertions and geospatial bbox queries."""

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig()
        # In-memory storage cache for mock/standalone mode
        self._memory_store: List[Dict] = []
        self._seed_default_store()

    def _seed_default_store(self):
        """Populate initial in-memory dataset for immediate frontend/API testing."""
        seeds = [
            {
                "id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[23.1500, 54.1200], [23.1550, 54.1200], [23.1550, 54.1250], [23.1500, 54.1250], [23.1500, 54.1200]]]
                },
                "classification": "Radar_Dome",
                "confidence": 0.965,
                "detection_date": "2026-05-15T08:30:00Z",
                "source_imagery": {"item_id": "S2A_MSIL2A_20260515_T34UFB", "platform": "sentinel-2a"}
            },
            {
                "id": "b2c3d4e5-f6a7-48b9-c012-3456789abcde",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[23.1800, 54.1000], [23.2100, 54.1000], [23.2100, 54.1150], [23.1800, 54.1150], [23.1800, 54.1000]]]
                },
                "classification": "Logistics_Depot",
                "confidence": 0.912,
                "detection_date": "2026-06-02T11:15:00Z",
                "source_imagery": {"item_id": "S2B_MSIL2A_20260602_T34UFB", "platform": "sentinel-2b"}
            },
            {
                "id": "c3d4e5f6-a7b8-49c0-d123-456789abcdef",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[23.3000, 54.2000], [23.3600, 54.2050], [23.3550, 54.2150], [23.2950, 54.2100], [23.3000, 54.2000]]]
                },
                "classification": "Airfield_Runway",
                "confidence": 0.984,
                "detection_date": "2026-07-10T14:00:00Z",
                "source_imagery": {"item_id": "S2A_MSIL2A_20260710_T34UFB", "platform": "sentinel-2a"}
            },
            {
                "id": "d4e5f6a7-b8c9-40d1-e234-56789abcdef0",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[23.2200, 54.1300], [23.2350, 54.1300], [23.2350, 54.1420], [23.2200, 54.1420], [23.2200, 54.1300]]]
                },
                "classification": "SAM_Battery_Site",
                "confidence": 0.941,
                "detection_date": "2026-08-22T09:45:00Z",
                "source_imagery": {"item_id": "S2B_MSIL2A_20260822_T34UFB", "platform": "sentinel-2b"}
            },
            {
                "id": "e5f6a7b8-c9d0-41e2-f345-6789abcdef01",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[23.1900, 54.1180], [23.2050, 54.1180], [23.2050, 54.1280], [23.1900, 54.1280], [23.1900, 54.1180]]]
                },
                "classification": "Hardened_Shelter",
                "confidence": 0.893,
                "detection_date": "2026-09-18T10:20:00Z",
                "source_imagery": {"item_id": "S2A_MSIL2A_20260918_T34UFB", "platform": "sentinel-2a"}
            }
        ]
        self._memory_store.extend(seeds)

    def insert_detection(
        self,
        id_str: str,
        geometry_geojson: Dict,
        classification: str,
        confidence: float,
        detection_date: str,
        source_imagery: Dict
    ):
        """Insert a detected infrastructure vector record."""
        record = {
            "id": id_str,
            "geometry": geometry_geojson,
            "classification": classification,
            "confidence": confidence,
            "detection_date": detection_date,
            "source_imagery": source_imagery
        }
        self._memory_store.append(record)
        logger.info("Inserted infrastructure detection", id=id_str, classification=classification)

    def query_geojson_feature_collection(
        self,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
        classes: Optional[List[str]] = None,
        min_confidence: float = 0.0
    ) -> Dict:
        """Query detections and package as standard GeoJSON FeatureCollection for Deck.gl."""
        features = []
        for item in self._memory_store:
            if item["confidence"] < min_confidence:
                continue
            if classes and item["classification"] not in classes:
                continue
            if min_date and item["detection_date"] < min_date:
                continue
            if max_date and item["detection_date"] > max_date:
                continue

            features.append({
                "type": "Feature",
                "id": item["id"],
                "geometry": item["geometry"],
                "properties": {
                    "id": item["id"],
                    "classification": item["classification"],
                    "confidence": item["confidence"],
                    "detection_date": item["detection_date"],
                    "source_imagery": item["source_imagery"]
                }
            })

        return {
            "type": "FeatureCollection",
            "features": features
        }
