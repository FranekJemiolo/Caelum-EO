"""Copernicus Data Space Ecosystem (CDSE) STAC API Client.

Queries Sentinel-1 and Sentinel-2 imagery bounding boxes across geopolitical geofences
and extracts required foundation model assets without fetching heavy rasters.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import pystac_client
import requests
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from services.ingestion.config import (
    Geofence,
    IngestionConfig,
    STACAssetMeta,
    STACItemPayload,
    settings,
)

logger = structlog.get_logger(__name__)


class CDSEStacClient:
    """Client for querying the Copernicus Data Space STAC catalog."""

    def __init__(self, config: Optional[IngestionConfig] = None):
        self.config = config or settings
        self.api_url = self.config.cdse_stac_api_url
        self._client: Optional[pystac_client.Client] = None

    @property
    def client(self) -> pystac_client.Client:
        """Lazy initialization of pystac client with retry protection."""
        if self._client is None:
            logger.info("Initializing CDSE STAC client", url=self.api_url)
            self._client = pystac_client.Client.open(self.api_url)
        return self._client

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        retry=retry_if_exception_type((requests.exceptions.RequestException, ConnectionError)),
        reraise=True,
    )
    def search_geofence(
        self,
        geofence: Geofence,
        start_time: datetime,
        end_time: datetime,
        collections: Optional[List[str]] = None,
        max_cloud_cover: Optional[float] = None,
        limit: int = 50,
    ) -> List[STACItemPayload]:
        """Query STAC API for Sentinel-1 and Sentinel-2 items within a geofence.

        Args:
            geofence: The surveillance zone with bounding box coordinates.
            start_time: Start of search time window (UTC).
            end_time: End of search time window (UTC).
            collections: List of STAC collection IDs (defaults to SENTINEL-2 and SENTINEL-1).
            max_cloud_cover: Maximum acceptable cloud cover percentage (0-100).
            limit: Maximum items to retrieve per page.

        Returns:
            List of strongly-typed STACItemPayload models ready for Kafka queuing.
        """
        if collections is None:
            # CDSE standard collection naming
            collections = ["SENTINEL-2", "SENTINEL-1"]

        cloud_limit = (
            max_cloud_cover if max_cloud_cover is not None else self.config.default_cloud_cover_max
        )
        datetime_range = (
            f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

        logger.info(
            "Executing STAC query",
            geofence_id=geofence.id,
            bbox=geofence.bbox,
            datetime_range=datetime_range,
            collections=collections,
            max_cloud_cover=cloud_limit,
        )

        try:
            search = self.client.search(
                collections=collections,
                bbox=geofence.bbox,
                datetime=datetime_range,
                max_items=limit,
            )

            results: List[STACItemPayload] = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for item in search.items():
                props = item.properties
                cloud_cover = props.get("cloudCover") or props.get("eo:cloud_cover")

                # Filter out optical scenes exceeding cloud cover limit
                collection_name = item.collection_id or ""
                if "SENTINEL-2" in collection_name.upper() and cloud_cover is not None:
                    if float(cloud_cover) > cloud_limit:
                        logger.debug(
                            "Skipping item due to excessive cloud cover",
                            item_id=item.id,
                            cloud_cover=cloud_cover,
                            max_allowed=cloud_limit,
                        )
                        continue

                # Filter and normalize relevant asset bands
                filtered_assets = self._extract_required_assets(item)

                # Extract MGRS Tile ID if available
                mgrs_tile = props.get("s2:mgrs_tile") or props.get("mgrs:utm_zone")
                if not mgrs_tile and "mgrs" in props:
                    mgrs_tile = str(props["mgrs"])

                payload = STACItemPayload(
                    item_id=item.id,
                    collection=collection_name,
                    datetime=item.datetime.isoformat() if item.datetime else now_iso,
                    bbox=list(item.bbox) if item.bbox else geofence.bbox,
                    geometry=item.geometry if item.geometry else {},
                    cloud_cover=float(cloud_cover) if cloud_cover is not None else None,
                    platform=props.get("platform"),
                    constellation=props.get("constellation"),
                    mgrs_tile=mgrs_tile,
                    geofence_id=geofence.id,
                    assets=filtered_assets,
                    published_at=now_iso,
                )
                results.append(payload)

            logger.info("STAC query complete", geofence_id=geofence.id, matched_items=len(results))
            return results

        except Exception as exc:
            logger.error("Error executing STAC query", geofence_id=geofence.id, error=str(exc))
            raise

    def _extract_required_assets(self, item) -> Dict[str, STACAssetMeta]:
        """Extract URLs for bands required by Prithvi and SAR processing.

        For Sentinel-2: Blue (B02), Green (B03), Red (B04), NIR (B8A), SWIR1 (B11), SWIR2 (B12).
        For Sentinel-1: VV, VH.
        """
        extracted: Dict[str, STACAssetMeta] = {}
        target_keys = set(self.config.sentinel2_bands + self.config.sentinel1_bands)

        for key, asset in item.assets.items():
            normalized_key = key.upper()
            # Direct match or band alias match
            if normalized_key in target_keys or key in target_keys:
                extracted[key] = STACAssetMeta(
                    href=asset.href, type=asset.media_type, title=asset.title
                )
            # Handle CDSE specific asset key naming if nested
            elif any(target in normalized_key for target in target_keys):
                extracted[key] = STACAssetMeta(
                    href=asset.href, type=asset.media_type, title=asset.title
                )

        # If no specific bands matched (e.g. single product archive), keep visual or default assets
        if not extracted:
            for k in ["visual", "data", "PRODUCT"]:
                if k in item.assets:
                    extracted[k] = STACAssetMeta(
                        href=item.assets[k].href,
                        type=item.assets[k].media_type,
                        title=item.assets[k].title,
                    )

        return extracted
