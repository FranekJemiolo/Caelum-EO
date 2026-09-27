#!/usr/bin/env python3
"""Generate deterministic multi-band GeoTIFF pairs simulating GEOINT infrastructure build-outs.

Creates co-registered T0 (baseline) and T1 (monitoring) GeoTIFF rasters with EPSG:4326 metadata.
- T0: Natural baseline terrain (forest/field/soil).
- T1: Introduced infrastructure (asphalt runway extension, concrete depot apron, radar facility).
- Bands: B02, B03, B04, B8A, B11, B12, and SCL (Scene Classification Layer).

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import rasterio
import structlog
from rasterio.transform import from_bounds

logger = structlog.get_logger(__name__)

# Default Surveillance Test Corridor: Suwalki Strategic Corridor (Eastern Europe)
DEFAULT_BBOX = [23.10, 54.05, 23.35, 54.25]  # [min_lon, min_lat, max_lon, max_lat]
DEFAULT_WIDTH = 256
DEFAULT_HEIGHT = 256

BAND_NAMES = ["B02", "B03", "B04", "B8A", "B11", "B12"]


def create_synthetic_scene_pair(
    height: int = DEFAULT_HEIGHT, width: int = DEFAULT_WIDTH, seed: int = 42
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
    scl_mask[runway_r1:runway_r2, runway_c1:runway_c2] = 5  # Bare/artificial surface
    scl_mask[radar_r1:radar_r2, radar_c1:radar_c2] = 5

    # Add small cloud patch in corner (classes 8 and 9) to verify cloud-masking logic
    scl_mask[5:20, 5:25] = 9

    return t0_cube, t1_cube, scl_mask


def write_scene_geotiffs(
    output_dir: Path,
    t0_cube: np.ndarray,
    t1_cube: np.ndarray,
    scl_mask: np.ndarray,
    bbox: list = DEFAULT_BBOX,
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
        "nodata": 0,
    }

    manifest: Dict[str, Dict[str, str]] = {"T0": {}, "T1": {}}

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


def generate_mock_zones(output_dir: Path) -> Path:
    """Generate sample strategic geographic zones GeoJSON."""
    zones_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "ZONE-SUWALKI-CORRIDOR",
                "properties": {
                    "id": "ZONE-SUWALKI-CORRIDOR",
                    "name": "Suwalki Gap Strategic Corridor",
                    "alert_level": "HIGH",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [23.00, 54.00],
                            [23.50, 54.00],
                            [23.50, 54.40],
                            [23.00, 54.40],
                            [23.00, 54.00],
                        ]
                    ],
                },
            },
            {
                "type": "Feature",
                "id": "ZONE-NORTH-SECTOR",
                "properties": {
                    "id": "ZONE-NORTH-SECTOR",
                    "name": "Northern Frontier Observation Sector",
                    "alert_level": "ELEVATED",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [23.00, 54.40],
                            [23.50, 54.40],
                            [23.50, 54.70],
                            [23.00, 54.70],
                            [23.00, 54.40],
                        ]
                    ],
                },
            },
            {
                "type": "Feature",
                "id": "ZONE-WEST-LOGISTICS",
                "properties": {
                    "id": "ZONE-WEST-LOGISTICS",
                    "name": "Western Staging Logistics Sector",
                    "alert_level": "NORMAL",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [22.60, 53.90],
                            [23.00, 53.90],
                            [23.00, 54.30],
                            [22.60, 54.30],
                            [22.60, 53.90],
                        ]
                    ],
                },
            },
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    zones_path = output_dir / "zones.geojson"
    zones_path.write_text(json.dumps(zones_geojson, indent=2))
    logger.info("Sample geographic zones generated", path=str(zones_path))
    return zones_path


def generate_mock_chips(
    chips_dir: Path, t0_cube: np.ndarray, t1_cube: np.ndarray
) -> Dict[str, Dict[str, str]]:
    """Generate high-resolution visual PNG chips (t0, t1, mask) for triage verification."""
    from PIL import Image

    chips_dir.mkdir(parents=True, exist_ok=True)
    sample_detections = {
        "a1b2c3d4-e5f6-47a8-b901-23456789abcd": {"r": (150, 205), "c": (130, 185)},
        "b2c3d4e5-f6a7-48b9-c012-3456789abcde": {"r": (30, 85), "c": (40, 110)},
        "c3d4e5f6-a7b8-49c0-d123-456789abcdef": {"r": (35, 75), "c": (45, 215)},
        "d4e5f6a7-b8c9-40d1-e234-56789abcdef0": {"r": (80, 135), "c": (90, 145)},
        "e5f6a7b8-c9d0-41e2-f345-6789abcdef01": {"r": (100, 155), "c": (110, 165)},
    }

    def _normalize_rgb(bands):
        # Bands: Red (index 2), Green (index 1), Blue (index 0)
        rgb = np.stack([bands[2], bands[1], bands[0]], axis=-1).astype(np.float32)
        rgb = np.clip(rgb / 3500.0 * 255.0, 0, 255).astype(np.uint8)
        return rgb

    manifest = {}
    for det_id, coords in sample_detections.items():
        sub_dir = chips_dir / det_id[:8]
        sub_dir.mkdir(parents=True, exist_ok=True)

        r1, r2 = coords["r"]
        c1, c2 = coords["c"]

        t0_crop = _normalize_rgb(t0_cube[:, r1:r2, c1:c2])
        t1_crop = _normalize_rgb(t1_cube[:, r1:r2, c1:c2])

        # Compute difference mask
        diff = np.abs(t1_crop.astype(np.int16) - t0_crop.astype(np.int16)).mean(axis=-1)
        mask = (diff > 30).astype(np.uint8) * 255

        # Create overlay mask (highlight in cyan RGBA)
        mask_rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
        mask_rgba[mask > 0] = [0, 242, 254, 200]

        t0_path = sub_dir / "t0.png"
        t1_path = sub_dir / "t1.png"
        mask_path = sub_dir / "mask.png"

        Image.fromarray(t0_crop).save(t0_path)
        Image.fromarray(t1_crop).save(t1_path)
        Image.fromarray(mask_rgba, mode="RGBA").save(mask_path)

        manifest[det_id] = {
            "t0_path": str(t0_path),
            "t1_path": str(t1_path),
            "mask_path": str(mask_path),
        }

    logger.info("Mock visual verification chips generated", total_targets=len(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic Sentinel-2 GeoTIFFs, zones, and visual chips"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./data/mock",
        help="Directory to store generated GeoTIFF files",
    )
    parser.add_argument(
        "--chips-dir",
        type=str,
        default="./data/chips",
        help="Directory to store visual verification chips",
    )
    args = parser.parse_args()

    out_path = Path(args.output_dir)
    chips_path = Path(args.chips_dir)

    t0, t1, scl = create_synthetic_scene_pair()
    manifest = write_scene_geotiffs(out_path, t0, t1, scl)
    generate_mock_zones(out_path)
    generate_mock_chips(chips_path, t0, t1)

    print("Successfully generated synthetic multi-temporal Sentinel-2 GeoTIFF pairs:")
    print(f" - Baseline T0: {len(manifest['T0'])} files in {out_path / 'T0_baseline'}")
    print(f" - Monitor  T1: {len(manifest['T1'])} files in {out_path / 'T1_monitor'}")
    print(f" - Strategic Zones: {out_path / 'zones.geojson'}")
    print(f" - Visual Chips: {chips_path}")


if __name__ == "__main__":
    main()
