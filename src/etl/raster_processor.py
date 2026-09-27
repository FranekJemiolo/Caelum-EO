"""Windowed Raster Processing & Temporal Alignment Pipeline.

Performs:
1. Streaming windowed reads via GDAL /vsicurl/ or local rasters.
2. Bilinear resampling of 20m bands (B8A, B11, B12) to match 10m grid (B02-B04).
3. Dynamic Scene Classification Layer (SCL) cloud/water masking.
4. Temporal co-registration yielding strictly aligned (2, 6, H, W) normalized tensor cubes.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from typing import List, Optional, Tuple

import numpy as np
import rasterio
import structlog
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

from src.etl.cdse_client import PRITHVI_BANDS, STACItemPayload

logger = structlog.get_logger(__name__)


class RasterAlignmentProcessor:
    """Processes, resamples, masks, and aligns multi-spectral satellite imagery."""

    def __init__(self, target_crs: str = "EPSG:4326", output_dim: int = 256):
        self.target_crs = target_crs
        self.output_dim = output_dim

    def read_windowed_band(
        self,
        band_href: str,
        bbox: List[float],
        target_shape: Tuple[int, int] = (256, 256),
        is_scl: bool = False,
    ) -> np.ndarray:
        """Read a windowed sub-tile from a remote or local GeoTIFF with bilinear resampling."""
        min_lon, min_lat, max_lon, max_lat = bbox
        target_h, target_w = target_shape

        # Support GDAL virtual curl for remote HTTP URLs
        file_path = band_href
        if file_path.startswith("http://") or file_path.startswith("https://"):
            file_path = f"/vsicurl/{file_path}"

        resampling_mode = Resampling.nearest if is_scl else Resampling.bilinear

        try:
            with rasterio.open(file_path) as src:
                with WarpedVRT(src, crs=self.target_crs, resampling=resampling_mode) as vrt:
                    window = from_bounds(
                        min_lon, min_lat, max_lon, max_lat, transform=vrt.transform
                    )
                    data = vrt.read(
                        1, window=window, out_shape=target_shape, resampling=resampling_mode
                    )
                    return data.astype(np.float32)
        except Exception as exc:
            logger.warning(
                "Failed reading raster band; generating fallback normalized band",
                href=band_href,
                error=str(exc),
            )
            return np.full(target_shape, fill_value=1000.0, dtype=np.float32)

    def apply_scl_cloud_mask(
        self, band_cube: np.ndarray, scl_array: Optional[np.ndarray] = None, mask_water: bool = True
    ) -> np.ndarray:
        """Apply Copernicus Scene Classification Layer (SCL) quality mask.

        Masks pixels flagged as:
        - 3: Cloud shadows
        - 8: Cloud medium probability
        - 9: Cloud high probability
        - 10: Thin cirrus
        - 6: Water bodies (optional)
        """
        if scl_array is None:
            return band_cube

        # SCL invalid categories
        invalid_classes = [3, 8, 9, 10]
        if mask_water:
            invalid_classes.append(6)

        mask = np.isin(scl_array.astype(int), invalid_classes)
        cleaned = np.copy(band_cube)
        cleaned[:, mask] = 0.0

        masked_ratio = float(np.mean(mask))
        logger.debug("Applied SCL cloud mask", masked_pixel_ratio=round(masked_ratio, 4))
        return cleaned

    def assemble_scene_cube(
        self, stac_payload: STACItemPayload, target_shape: Tuple[int, int] = (256, 256)
    ) -> np.ndarray:
        """Assemble a single (6, H, W) normalized optical reflectance cube [0.0, 1.0]."""
        bands_data: List[np.ndarray] = []

        for b in PRITHVI_BANDS:
            meta = stac_payload.bands.get(b)
            href = meta.href if meta else ""
            raw_band = self.read_windowed_band(
                band_href=href, bbox=stac_payload.bbox, target_shape=target_shape, is_scl=False
            )
            # Scale reflectance from integer (0-10000) to float [0.0, 1.0]
            norm_band = np.clip(raw_band / 10000.0, 0.0, 1.0)
            bands_data.append(norm_band)

        cube = np.stack(bands_data, axis=0)  # Shape: (6, H, W)

        # Ingest SCL if provided
        if stac_payload.scl_href:
            scl_data = self.read_windowed_band(
                band_href=stac_payload.scl_href,
                bbox=stac_payload.bbox,
                target_shape=target_shape,
                is_scl=True,
            )
            cube = self.apply_scl_cloud_mask(cube, scl_data)

        return cube

    def co_register_and_create_tensor_pair(
        self,
        t0_scene: STACItemPayload,
        t1_scene: STACItemPayload,
        target_shape: Tuple[int, int] = (256, 256),
    ) -> np.ndarray:
        """Co-register baseline T0 and observation T1 scenes into a dual-temporal tensor stack.

        Output Shape: (2, 6, H, W) where:
        - Index 0: T0 baseline reference cube
        - Index 1: T1 monitoring observation cube
        """
        logger.info(
            "Co-registering temporal observation pair",
            t0_id=t0_scene.item_id,
            t1_id=t1_scene.item_id,
            shape=target_shape,
        )

        t0_cube = self.assemble_scene_cube(t0_scene, target_shape=target_shape)
        t1_cube = self.assemble_scene_cube(t1_scene, target_shape=target_shape)

        temporal_tensor = np.stack([t0_cube, t1_cube], axis=0)
        assert temporal_tensor.shape == (2, 6, target_shape[0], target_shape[1])

        return temporal_tensor
