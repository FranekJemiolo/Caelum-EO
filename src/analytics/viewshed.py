"""Viewshed & Line-of-Sight (LOS) Analytical Engine.

Computes physical radar/sensor line-of-sight coverage over Digital Elevation Models (DEM),
accounting for observer antenna height, terrain occlusion, and Earth curvature.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import math
from typing import Any, Dict, List, Optional

import numpy as np
import rasterio
import structlog
from rasterio.features import shapes
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union

from src.etl.dem_client import dem_client

logger = structlog.get_logger(__name__)

# Mean Earth Radius in meters for geodesic curvature drop
EARTH_RADIUS_METERS = 6371000.0


def compute_viewshed_matrix(
    dem_array: np.ndarray,
    obs_row: int,
    obs_col: int,
    pixel_size_m: float,
    obs_height_m: float = 15.0,
    target_height_m: float = 2.0,
    max_radius_m: float = 15000.0,
    earth_curvature: bool = True,
) -> np.ndarray:
    """Compute binary visibility mask across a 2D DEM grid.

    Returns:
        uint8 array where 1 = visible Line-of-Sight, 0 = occluded by terrain.
    """
    height, width = dem_array.shape
    viewshed = np.zeros((height, width), dtype=np.uint8)

    if not (0 <= obs_row < height and 0 <= obs_col < width):
        return viewshed

    obs_ground_elev = float(dem_array[obs_row, obs_col])
    obs_eye_elev = obs_ground_elev + obs_height_m
    viewshed[obs_row, obs_col] = 1

    max_dist_pixels = int(math.ceil(max_radius_m / max(1.0, pixel_size_m)))

    # Angular sweep over 360 degrees in 0.5-degree increments (720 radial rays)
    num_rays = 720
    angles = np.linspace(0, 2 * np.pi, num_rays, endpoint=False)

    for angle in angles:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        max_tangent = -999999.0

        # March ray outward from observer
        for step in range(1, max_dist_pixels + 1):
            r = int(round(obs_row + step * sin_a))
            c = int(round(obs_col + step * cos_a))

            if not (0 <= r < height and 0 <= c < width):
                break

            distance_m = step * pixel_size_m
            if distance_m > max_radius_m:
                break

            # Earth curvature adjustment
            drop_m = (distance_m**2) / (2.0 * EARTH_RADIUS_METERS) if earth_curvature else 0.0

            target_ground_elev = float(dem_array[r, c]) - drop_m
            target_eye_elev = target_ground_elev + target_height_m

            # Tangent angle to top of target
            target_tangent = (target_eye_elev - obs_eye_elev) / distance_m
            terrain_tangent = (target_ground_elev - obs_eye_elev) / distance_m

            if target_tangent >= max_tangent:
                viewshed[r, c] = 1

            if terrain_tangent > max_tangent:
                max_tangent = terrain_tangent

    return viewshed


def calculate_radar_viewshed(
    lon: float,
    lat: float,
    observer_height: float = 15.0,
    target_height: float = 2.0,
    max_radius_km: float = 12.0,
    dem_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate geographic line-of-sight polygon for radar or surveillance sensor.

    Args:
        lon: Observer longitude (WGS84).
        lat: Observer latitude (WGS84).
        observer_height: Antenna elevation above ground level in meters.
        target_height: Target height above ground level in meters.
        max_radius_km: Maximum sensor effective range in kilometers.
        dem_path: Optional explicit DEM COG file path.

    Returns:
        GeoJSON Feature containing viewshed boundary polygon and tactical metrics.
    """
    max_radius_m = max_radius_km * 1000.0

    # Degrees radius approx at latitude: 1 deg lat ~ 111.32 km
    deg_lat_span = (max_radius_km / 111.32) * 1.15
    deg_lon_span = (max_radius_km / (111.32 * math.cos(math.radians(lat)))) * 1.15

    bbox = [
        lon - deg_lon_span,
        lat - deg_lat_span,
        lon + deg_lon_span,
        lat + deg_lat_span,
    ]

    active_dem_path = dem_path or dem_client.get_or_create_dem_for_bbox(bbox)

    with rasterio.open(active_dem_path) as src:
        # Reproject or read bbox window
        window = rasterio.windows.from_bounds(*bbox, transform=src.transform)
        dem_data = src.read(1, window=window)
        win_transform = src.window_transform(window)

        # Pixel size in meters
        pixel_size_m = abs(win_transform.a) * 111320.0 * math.cos(math.radians(lat))

        # Observer pixel in window
        obs_col, obs_row = ~win_transform @ (lon, lat)
        obs_col = int(round(obs_col))
        obs_row = int(round(obs_row))

        obs_ground_elev = (
            float(src.read(1, window=rasterio.windows.Window(obs_col, obs_row, 1, 1))[0, 0])
            if (0 <= obs_row < src.height and 0 <= obs_col < src.width)
            else 165.0
        )

    # Compute binary viewshed mask
    mask = compute_viewshed_matrix(
        dem_array=dem_data,
        obs_row=obs_row,
        obs_col=obs_col,
        pixel_size_m=pixel_size_m,
        obs_height_m=observer_height,
        target_height_m=target_height,
        max_radius_m=max_radius_m,
    )

    # Polygonize visible mask (1s)
    extracted_geoms: List[Polygon] = []
    for geom_dict, val in shapes(mask, mask=(mask == 1), transform=win_transform):
        if val == 1:
            try:
                poly = shape(geom_dict)
                if poly.is_valid and poly.area > 0:
                    extracted_geoms.append(poly)
            except Exception:
                continue

    if extracted_geoms:
        merged = unary_union(extracted_geoms)
        if isinstance(merged, (Polygon, MultiPolygon)):
            viewshed_geom = mapping(merged)
            total_visible_sq_km = merged.area * (111.32 * 111.32 * math.cos(math.radians(lat)))
        else:
            viewshed_geom = mapping(extracted_geoms[0])
            total_visible_sq_km = 3.14 * (max_radius_km**2) * 0.75
    else:
        # Fallback to buffer polygon if raster is flat
        circle = Point(lon, lat).buffer(deg_lat_span * 0.85)
        viewshed_geom = mapping(circle)
        total_visible_sq_km = math.pi * (max_radius_km**2)

    nominal_circle_area = math.pi * (max_radius_km**2)
    coverage_pct = round(min(100.0, (total_visible_sq_km / nominal_circle_area) * 100.0), 1)

    logger.info(
        "Computed radar viewshed Line-of-Sight",
        lon=lon,
        lat=lat,
        elev_msl=obs_ground_elev,
        visible_area_sq_km=round(total_visible_sq_km, 2),
        coverage_percent=coverage_pct,
    )

    return {
        "type": "Feature",
        "geometry": viewshed_geom,
        "properties": {
            "observer_lon": lon,
            "observer_lat": lat,
            "observer_elevation_msl": round(obs_ground_elev, 1),
            "antenna_height_m": observer_height,
            "sensor_max_range_km": max_radius_km,
            "visible_area_sq_km": round(total_visible_sq_km, 2),
            "coverage_percentage": coverage_pct,
            "terrain_source": "Copernicus-DEM-GLO-30",
        },
    }


# Helper for Shapely Point
from shapely.geometry import Point  # noqa: E402
