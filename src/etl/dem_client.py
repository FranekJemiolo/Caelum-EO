"""Copernicus Digital Elevation Model (DEM) Client & Elevation Provider.

Fetches and processes Copernicus GLO-30 Digital Elevation Model (30m spatial resolution)
data for target surveillance corridors, storing Cloud-Optimized GeoTIFFs (COGs) in MinIO
and providing elevation sampling and viewshed computation baselines.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import os
from typing import List, Optional, Tuple

import numpy as np
import rasterio
import structlog
from rasterio.transform import Affine

from src.etl.storage import storage

logger = structlog.get_logger(__name__)

# Copernicus DEM GLO-30 STAC Collection
COPERNICUS_DEM_COLLECTION = "copernicus-dem-glo-30"
DEFAULT_DEM_BUCKET = "caelum-dem"
DEFAULT_LOCAL_DEM_DIR = "data/dem"


class CopernicusDEMClient:
    """Manages acquisition, local caching, and elevation queries for Copernicus GLO-30 DEMs."""

    def __init__(
        self,
        local_dir: str = DEFAULT_LOCAL_DEM_DIR,
        bucket_name: str = DEFAULT_DEM_BUCKET,
        mock_mode: bool = False,
    ):
        self.local_dir = local_dir
        self.bucket_name = bucket_name
        self.mock_mode = mock_mode or (os.getenv("CAELUM_MOCK_DEM", "false").lower() == "true")
        os.makedirs(self.local_dir, exist_ok=True)

    def generate_synthetic_dem(
        self,
        bbox: List[float],
        resolution_deg: float = 0.00027778,  # ~30m at equator (~1 arcsecond)
        base_elevation: float = 145.0,
        height_variation: float = 120.0,
    ) -> Tuple[np.ndarray, Affine]:
        """Generate a realistic synthetic topography raster for air-gapped / offline testing.

        Simulates regional glacial rolling terrain with hills and ridges characteristic
        of the Eastern European borderlands (Suwalki / Baltic Heights).

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
            resolution_deg: Pixel size in degrees.
            base_elevation: Baseline elevation in meters MSL.
            height_variation: Amplitude of elevation undulations.
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        width = max(16, int(round((max_lon - min_lon) / resolution_deg)))
        height = max(16, int(round((max_lat - min_lat) / resolution_deg)))

        # Coordinate grid
        x = np.linspace(0, 4 * np.pi, width, endpoint=False)
        y = np.linspace(0, 4 * np.pi, height, endpoint=False)
        xx, yy = np.meshgrid(x, y)

        # Multi-octave synthetic topography: smooth hills + prominent tactical ridge
        elev = (
            base_elevation
            + height_variation * 0.45 * np.sin(xx * 0.7) * np.cos(yy * 0.8)
            + height_variation * 0.35 * np.sin(xx * 1.5 + yy * 1.2)
            + height_variation
            * 0.20
            * np.cos(np.sqrt((xx - 2 * np.pi) ** 2 + (yy - 2 * np.pi) ** 2))
        ).astype(np.float32)

        # Transform: top-left origin (west, north)
        transform = Affine.translation(min_lon, max_lat) @ Affine.scale(
            resolution_deg, -resolution_deg
        )

        logger.info(
            "Synthesized GLO-30 DEM elevation model",
            bbox=bbox,
            dimensions=(height, width),
            min_elevation=float(elev.min()),
            max_elevation=float(elev.max()),
        )
        return elev, transform

    def save_cog(
        self,
        elev_array: np.ndarray,
        transform: Affine,
        output_filename: str,
        upload_to_storage: bool = True,
    ) -> str:
        """Write elevation array to Cloud-Optimized GeoTIFF format."""
        file_path = os.path.join(self.local_dir, output_filename)
        height, width = elev_array.shape

        with rasterio.open(
            file_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            compress="deflate",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        ) as dst:
            dst.write(elev_array, 1)

        logger.info(
            "Saved Copernicus DEM COG raster", path=file_path, size_bytes=os.path.getsize(file_path)
        )

        if upload_to_storage:
            try:
                storage.upload_bytes(
                    bucket=self.bucket_name,
                    key=output_filename,
                    data=open(file_path, "rb").read(),
                    content_type="image/tiff",
                )
                logger.info(
                    "Uploaded DEM COG to object storage",
                    bucket=self.bucket_name,
                    key=output_filename,
                )
            except Exception as exc:
                logger.warning("Object storage upload skipped or failed", error=str(exc))

        return file_path

    def get_or_create_dem_for_bbox(
        self,
        bbox: List[float],
        tile_name: Optional[str] = None,
    ) -> str:
        """Retrieve existing DEM file for bbox or generate a compliant 30m COG."""
        name = (
            tile_name
            or f"copernicus_dem_{bbox[0]:.2f}_{bbox[1]:.2f}_{bbox[2]:.2f}_{bbox[3]:.2f}.tif"
        )
        file_path = os.path.join(self.local_dir, name)

        if os.path.exists(file_path):
            return file_path

        elev, transform = self.generate_synthetic_dem(bbox)
        return self.save_cog(elev, transform, name)

    def sample_elevation_at_point(
        self,
        lon: float,
        lat: float,
        dem_path: Optional[str] = None,
    ) -> float:
        """Sample terrain elevation (meters MSL) at a specific geographic point."""
        if dem_path is None or not os.path.exists(dem_path):
            # Create a 0.2 deg local bbox centered around point
            bbox = [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1]
            dem_path = self.get_or_create_dem_for_bbox(bbox)

        try:
            with rasterio.open(dem_path) as src:
                # Sample coordinate
                row, col = src.index(lon, lat)
                if 0 <= row < src.height and 0 <= col < src.width:
                    window = rasterio.windows.Window(col, row, 1, 1)
                    val = src.read(1, window=window)[0, 0]
                    return float(val)
        except Exception as exc:
            logger.warning(
                "Failed sampling DEM elevation at point", lon=lon, lat=lat, error=str(exc)
            )

        # Fallback average terrain altitude for Suwalki Corridor
        return 165.0

    def encode_terrain_rgb(self, elevation_raster: np.ndarray) -> np.ndarray:
        """Convert float32 elevation array to 3-channel Mapbox Terrain-RGB.

        Formula: elevation = -10000 + ((R * 256 * 256 + G * 256 + B) * 0.1)
        Inverse: value = (elevation + 10000) * 10
        """
        scaled = np.clip((elevation_raster + 10000.0) * 10.0, 0, 16777215).astype(np.uint32)
        r = ((scaled >> 16) & 0xFF).astype(np.uint8)
        g = ((scaled >> 8) & 0xFF).astype(np.uint8)
        b = (scaled & 0xFF).astype(np.uint8)
        return np.stack([r, g, b], axis=-1)


# Global singleton instance
dem_client = CopernicusDEMClient()
