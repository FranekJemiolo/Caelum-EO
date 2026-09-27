#!/usr/bin/env python3
"""Generate deterministic multi-band GeoTIFF pairs simulating GEOINT infrastructure build-outs.

Creates co-registered T0 (baseline) and T1 (monitoring) GeoTIFF rasters with EPSG:4326 metadata.
- T0: Natural baseline terrain (forest/field/soil).
- T1: Introduced infrastructure (asphalt runway extension, concrete depot apron, radar facility).
- Bands: B02, B03, B04, B8A, B11, B12, and SCL (Scene Classification Layer).

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import argparse
import os
from pathlib import Path
from typing import Dict, Tuple
import numpy as np
import rasterio
from rasterio.transform import from_bounds
import structlog

logger = structlog.get_logger(__name__)

# Default Surveillance Test Corridor: Suwalki Strategic Corridor (Eastern Europe)
DEFAULT_BBOX = [23.10, 54.05, 23.35, 54.25]  # [min_lon, min_lat, max_lon, max_lat]
DEFAULT_WIDTH = 256
DEFAULT_HEIGHT = 256

BAND_NAMES = ["B02", "B03", "B04", "B8A", "B11", "B12"]


def create_synthetic_scene_pair(
    height: int = DEFAULT_HEIGHT,
    width: int = DEFAULT_WIDTH,
    seed: int = 42
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate normalized (6, H, W) optical reflectance stacks and SCL mask.

    Returns:
        Tuple of (t0_cube, t1_cube, scl_mask) where reflectance is scaled [0, 10000] uint16.
    """
    np.random.seed(seed)

    # 1. Generate T0 Baseline: Natural terrain (grass/forest/soil)
    # Band values in typical Sentinel-2 L2A BOA reflectance integers (1000 = 0.10 reflectance)
    # B02 (Blue): ~300-600, B03 (Green): ~500-900, B04 (Red): ~400-800
    # B8A (NIR): ~2500-4000 (vegetation peak), B11 (SWIR1): ~1500-2500, B12 (SWIR2): ~800-1600
    t0_cube = np.zeros((6, height, width), dtype=np.uint16)
    t0_cube[0] = np.random.normal(450, 50, (height, width)).clip(200, 800)
    t0_cube[1] = np.random.normal(700, 60, (height, width)).clip(300, 1200)
    t0_cube[2] = np.random.normal(550, 50, (height, width)).clip(250, 1000)
    t0_cube[3] = np.random.normal(3200, 200, (height, width)).clip(2000, 4500)
    t0_cube[4] = np.random.normal(1800, 150, (height, width)).clip(1000, 3000)
    t0_cube[5] = np.random.normal(1100, 100, (height, width)).clip(600, 2000)

    # 2. Generate T1: Introduce tactical infrastructure build-outs
    t1_cube = np.copy(t0_cube)

    # Anomaly 1: Paved Runway / Taxiway Extension (long rectangular structure)
    # Concrete/asphalt: High visible (~2500-3500), moderate NIR (~2500), high SWIR (~3000)
    runway_r1, runway_r2 = 40, 65
    runway_c1, runway_c2 = 50, 210
    t1_cube[0, runway_r1:runway_r2, runway_c1:runway_c2] = 2800  # High blue
    t1_cube[1, runway_r1:runway_r2, runway_c1:runway_c2] = 3000  # High green
    t1_cube[2, runway_r1:runway_r2, runway_c1:runway_c2] = 3200  # High red
    t1_cube[3, runway_r1:runway_r2, runway_c1:runway_c2] = 2600  # Flat NIR
    t1_cube[4, runway_r1:runway_r2, runway_c1:runway_c2] = 3400  # High SWIR1
    t1_cube[5, runway_r1:runway_r2, runway_c1:runway_c2] = 3100  # High SWIR2

    # Anomaly 2: Hardened Radar Facility / Geodesic Enclosure (compact square on high terrain)
    radar_r1, radar_r2 = 160, 195
    radar_c1, radar_c2 = 140, 175
    t1_cube[0, radar_r1:radar_r2, radar_c1:radar_c2] = 4500  # Very bright reflective dome
    t1_cube[1, radar_r1:radar_r2, radar_c1:radar_c2] = 4800
    t1_cube[2, radar_r1:radar_r2, radar_c1:radar_c2] = 5000
    t1_cube[3, radar_r1:radar_r2, radar_c1:radar_c2] = 4200
    t1_cube[4, radar_r1:radar_r2, radar_c1:radar_c2] = 4000
    t1_cube[5, radar_r1:radar_r2, radar_c1:radar_c2] = 3800

    # 3. Generate Scene Classification Layer (SCL)
    # SCL values: 4 = Vegetation, 5 = Bare soil, 8/9 = Clouds, 6 = Water
    scl_mask = np.full((height, width), fill_value=4, dtype=np.uint8)  # Predominantly vegetation
    scl_mask[runway_r1:runway_r2, runway_c1:runway_c2] = 5            # Bare/artificial surface
    scl_mask[radar_r1:radar_r2, radar_c1:radar_c2] = 5

    # Add small cloud patch in corner (classes 8 and 9) to verify cloud-masking logic
    scl_mask[5:20, 5:25] = 9

    return t0_cube, t1_cube, scl_mask


def write_scene_geotiffs(
    output_dir: Path,
    t0_cube: np.ndarray,
    t1_cube: np.ndarray,
    scl_mask: np.ndarray,
    bbox: list = DEFAULT_BBOX
) -> Dict[str, Dict[str, str]]:
    """Write individual Cloud-Optimized GeoTIFFs for each band to disk with valid EPSG:4326 metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    min_lon, min_lat, max_lon, max_lat = bbox
    height, width = t0_cube.shape[1], t0_cube.shape[2]
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": rasterio.uint16,
        "crs": "EPSG:4326",
        "transform": transform,
        "compress": "deflate",
        "nodata": 0
    }

    manifest = {"T0": {}, "T1": {}}

    # Write T0 Bands
    t0_dir = output_dir / "T0_baseline"
    t0_dir.mkdir(exist_ok=True)
    for i, band in enumerate(BAND_NAMES):
        band_path = t0_dir / f"{band}.tif"
        with rasterio.open(band_path, "w", **profile) as dst:
            dst.write(t0_cube[i], 1)
        manifest["T0"][band] = str(band_path)

    # Write T0 SCL
    scl_profile = profile.copy()
    scl_profile["dtype"] = rasterio.uint8
    t0_scl_path = t0_dir / "SCL.tif"
    with rasterio.open(t0_scl_path, "w", **scl_profile) as dst:
        dst.write(scl_mask, 1)
    manifest["T0"]["SCL"] = str(t0_scl_path)

    # Write T1 Bands
    t1_dir = output_dir / "T1_monitor"
    t1_dir.mkdir(exist_ok=True)
    for i, band in enumerate(BAND_NAMES):
        band_path = t1_dir / f"{band}.tif"
        with rasterio.open(band_path, "w", **profile) as dst:
            dst.write(t1_cube[i], 1)
        manifest["T1"][band] = str(band_path)

    # Write T1 SCL
    t1_scl_path = t1_dir / "SCL.tif"
    with rasterio.open(t1_scl_path, "w", **scl_profile) as dst:
        dst.write(scl_mask, 1)
    manifest["T1"]["SCL"] = str(t1_scl_path)

    logger.info("Synthetic multi-band GeoTIFFs generated", output_dir=str(output_dir))
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic Sentinel-2 GeoTIFFs")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./data/mock",
        help="Directory to store generated GeoTIFF files"
    )
    args = parser.parse_args()

    out_path = Path(args.output_dir)
    t0, t1, scl = create_synthetic_scene_pair()
    manifest = write_scene_geotiffs(out_path, t0, t1, scl)

    print("Successfully generated synthetic multi-temporal Sentinel-2 GeoTIFF pairs:")
    print(f" - Baseline T0: {len(manifest['T0'])} files in {out_path / 'T0_baseline'}")
    print(f" - Monitor  T1: {len(manifest['T1'])} files in {out_path / 'T1_monitor'}")


if __name__ == "__main__":
    main()
