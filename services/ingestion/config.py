"""Configuration settings and domain schemas for the STAC Ingestion Firehose.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Geofence(BaseModel):
    """Geographical region of interest for continuous surveillance."""

    id: str
    name: str
    # Bounding box in WGS84 [min_lon, min_lat, max_lon, max_lat]
    bbox: List[float] = Field(..., min_length=4, max_length=4)
    description: Optional[str] = None


class STACAssetMeta(BaseModel):
    """Asset href and media type metadata."""

    href: str
    type: Optional[str] = None
    title: Optional[str] = None


class STACItemPayload(BaseModel):
    """Standardized metadata message emitted to Kafka (geoint-stac-ingest).

    Massive GeoTIFFs are deliberately omitted from immediate transmission.
    Instead, exact asset URLs, spatial bounds, and cloud cover are queued.
    """

    item_id: str
    collection: str
    datetime: str
    bbox: List[float]
    geometry: Dict
    cloud_cover: Optional[float] = None
    platform: Optional[str] = None
    constellation: Optional[str] = None
    mgrs_tile: Optional[str] = None
    geofence_id: str
    assets: Dict[str, STACAssetMeta]
    published_at: str


class IngestionConfig(BaseSettings):
    """Central configuration for CDSE STAC client and Kafka publisher."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Kafka Settings
    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_topic_stac_ingest: str = Field(
        default="geoint-stac-ingest", alias="KAFKA_TOPIC_STAC_INGEST"
    )
    kafka_client_id: str = Field(default="caelum-stac-poller", alias="KAFKA_CLIENT_ID")
    kafka_acks: str = "all"
    kafka_retries: int = 5
    kafka_dry_run: bool = Field(default=False, alias="KAFKA_DRY_RUN")

    # Copernicus Data Space Ecosystem (CDSE) Settings
    cdse_stac_api_url: str = Field(
        default="https://catalogue.dataspace.copernicus.eu/stac", alias="CDSE_STAC_API_URL"
    )
    cdse_username: Optional[str] = Field(default=None, alias="CDSE_USERNAME")
    cdse_password: Optional[str] = Field(default=None, alias="CDSE_PASSWORD")

    # Polling Parameters
    default_cloud_cover_max: float = Field(default=20.0, alias="DEFAULT_CLOUD_COVER_MAX")
    poll_interval_seconds: int = Field(default=3600, alias="POLL_INTERVAL_SECONDS")
    lookback_days: int = Field(default=7, alias="LOOKBACK_DAYS")
    max_items_per_query: int = 50

    # Prithvi-EO 6-band requirements for Sentinel-2
    sentinel2_bands: List[str] = ["B02", "B03", "B04", "B8A", "B11", "B12"]
    # Sentinel-1 SAR polarizations
    sentinel1_bands: List[str] = ["VV", "VH"]

    # Pre-configured Geopolitical Monitoring Zones
    geofences: List[Geofence] = [
        Geofence(
            id="suwalki-gap",
            name="Suwalki Corridor Strategic Zone",
            bbox=[22.8, 53.8, 24.5, 54.7],
            description="Baltic-NATO transit corridor monitoring for forward operating bases and vehicle staging.",
        ),
        Geofence(
            id="crimea-chornomorske",
            name="Black Sea Naval Facilities",
            bbox=[32.4, 45.2, 33.7, 45.8],
            description="Deepwater pier, radar dome, and coastal defense installations.",
        ),
        Geofence(
            id="bab-el-mandeb",
            name="Bab-el-Mandeb Maritime Strait",
            bbox=[43.1, 12.4, 43.6, 12.9],
            description="Chokepoint littoral monitoring for coastal radar installations and landing infrastructure.",
        ),
    ]


# Singleton instance
settings = IngestionConfig()
