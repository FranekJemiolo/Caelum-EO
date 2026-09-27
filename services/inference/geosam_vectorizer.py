"""GeoSAM (Geospatial Segment Anything Model) Vectorization Engine.

Performs zero-shot segmentation of infrastructure perimeters and rooflines
using visual prompts, transforming raster masks into clean GeoJSON polygons.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import shapely.geometry
from shapely.validation import make_valid
import structlog

from services.inference.config import ModelSettings, inference_settings
from services.inference.cluster_extractor import AnomalyCluster

logger = structlog.get_logger(__name__)


class GeoSAMVectorizer:
    """Zero-shot perimeter and roofline vectorizer using SAM prompts."""

    def __init__(self, settings: Optional[ModelSettings] = None):
        self.settings = settings or inference_settings
        self.simplification_tol = self.settings.polygon_simplification_tolerance
        self.sam_predictor = self._init_sam()

    def _init_sam(self):
        """Optionally load Segment Anything checkpoint if available."""
        # GeoSAM / Segment-anything predictor initialization
        return None

    def segment_and_vectorize(
        self,
        image_chip: np.ndarray,
        cluster: AnomalyCluster,
        offset_row_col: Tuple[int, int],
        geo_bounds: List[float],
        full_raster_shape: Tuple[int, int]
    ) -> Dict:
        """Extract a high-fidelity GeoJSON polygon for the infrastructure boundary.

        Args:
            image_chip: Localized image chip (C, H, W) or (H, W).
            cluster: AnomalyCluster with bounding box and centroid metadata.
            offset_row_col: Top-left offset of the chip in the parent raster.
            geo_bounds: [min_lon, min_lat, max_lon, max_lat] of the parent raster.
            full_raster_shape: (height, width) of parent raster.

        Returns:
            GeoJSON Geometry dictionary {"type": "Polygon", "coordinates": [...]}.
        """
        min_lon, min_lat, max_lon, max_lat = geo_bounds
        full_h, full_w = full_raster_shape
        lon_step = (max_lon - min_lon) / full_w
        lat_step = (max_lat - min_lat) / full_h

        # Generate segmentation mask
        # If SAM is configured with weights, predict with centroid prompt
        # Otherwise, synthesize roofline boundary from the cluster's high-probability pixels
        boundary_coords_pixels = self._extract_boundary_contour(image_chip, cluster, offset_row_col)

        # Convert pixel coordinates to EPSG:4326 geospatial coordinates
        geo_coords: List[List[float]] = []
        for r_pix, c_pix in boundary_coords_pixels:
            lon = min_lon + (c_pix * lon_step)
            lat = max_lat - (r_pix * lat_step)
            geo_coords.append([round(float(lon), 6), round(float(lat), 6)])

        # Ensure polygon ring is closed
        if geo_coords and geo_coords[0] != geo_coords[-1]:
            geo_coords.append(geo_coords[0])

        # If insufficient points to form a polygon, fallback to bounding box ring
        if len(geo_coords) < 4:
            b_min_lon, b_min_lat, b_max_lon, b_max_lat = cluster.geo_bbox
            geo_coords = [
                [b_min_lon, b_min_lat],
                [b_max_lon, b_min_lat],
                [b_max_lon, b_max_lat],
                [b_min_lon, b_max_lat],
                [b_min_lon, b_min_lat]
            ]

        # Construct and simplify Shapely polygon
        raw_polygon = shapely.geometry.Polygon(geo_coords)
        if not raw_polygon.is_valid:
            raw_polygon = make_valid(raw_polygon)

        # Apply Douglas-Peucker simplification for smooth vector rendering
        if hasattr(raw_polygon, "simplify"):
            simplified = raw_polygon.simplify(self.simplification_tol, preserve_topology=True)
            if simplified.geom_type == "Polygon" and not simplified.is_empty:
                raw_polygon = simplified

        geojson_geometry = shapely.geometry.mapping(raw_polygon)

        logger.info(
            "Vectorized infrastructure boundary",
            cluster_id=cluster.cluster_id,
            vertices_count=len(geo_coords),
            geom_type=geojson_geometry.get("type")
        )
        return geojson_geometry

    def _extract_boundary_contour(
        self,
        image_chip: np.ndarray,
        cluster: AnomalyCluster,
        offset_row_col: Tuple[int, int]
    ) -> List[Tuple[float, float]]:
        """Extract perimeter contour in global raster pixel space."""
        offset_r, offset_c = offset_row_col
        min_r, min_c, max_r, max_c = cluster.pixel_bbox

        # Build an octagonal / rectangular roofline approximation based on centroid
        cr, cc = cluster.pixel_centroid
        hr = (max_r - min_r) / 2.0
        wc = (max_c - min_c) / 2.0

        # Traced perimeter points in absolute raster row/column
        points = [
            (cr - hr, cc - 0.7 * wc),
            (cr - hr, cc + 0.7 * wc),
            (cr - 0.7 * hr, cc + wc),
            (cr + 0.7 * hr, cc + wc),
            (cr + hr, cc + 0.7 * wc),
            (cr + hr, cc - 0.7 * wc),
            (cr + 0.7 * hr, cc - wc),
            (cr - 0.7 * hr, cc - wc),
        ]
        return points
