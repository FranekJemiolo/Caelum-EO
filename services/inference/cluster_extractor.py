"""Spatial Cluster & Bounding Box Extractor for Binary Change Masks.

Isolates structural anomaly clusters from large raster fields using connected component
labeling and derives georeferenced spatial bounding boxes and image chips.
Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import ndimage
from pydantic import BaseModel
import structlog

from services.inference.config import ModelSettings, inference_settings

logger = structlog.get_logger(__name__)


class AnomalyCluster(BaseModel):
    """Georeferenced anomaly cluster candidate."""
    cluster_id: int
    pixel_bbox: Tuple[int, int, int, int]  # (min_row, min_col, max_row, max_col)
    pixel_centroid: Tuple[float, float]    # (row, col)
    geo_bbox: List[float]                  # [min_lon, min_lat, max_lon, max_lat]
    geo_centroid: List[float]              # [lon, lat]
    pixel_count: int
    mean_confidence: float


class SpatialClusterExtractor:
    """Extracts coherent spatial anomaly clusters from Prithvi change masks."""

    def __init__(self, settings: Optional[ModelSettings] = None):
        self.settings = settings or inference_settings
        self.min_pixels = self.settings.min_cluster_pixels

    def extract_clusters(
        self,
        binary_mask: np.ndarray,
        prob_map: np.ndarray,
        geo_bounds: List[float]  # [min_lon, min_lat, max_lon, max_lat]
    ) -> List[AnomalyCluster]:
        """Group connected components of 1s in the binary mask and translate to geospatial coordinates.

        Args:
            binary_mask: Uint8 binary mask (H, W).
            prob_map: Float32 probability map (H, W).
            geo_bounds: Bounding box in EPSG:4326 [min_lon, min_lat, max_lon, max_lat].

        Returns:
            List of georeferenced AnomalyCluster instances.
        """
        min_lon, min_lat, max_lon, max_lat = geo_bounds
        height, width = binary_mask.shape

        # 8-connectivity structure
        structure = ndimage.generate_binary_structure(2, 2)
        labeled_mask, num_features = ndimage.label(binary_mask, structure=structure)

        clusters: List[AnomalyCluster] = []
        lon_step = (max_lon - min_lon) / width
        lat_step = (max_lat - min_lat) / height

        logger.info("Extracting anomaly clusters", total_connected_components=num_features)

        for cluster_id in range(1, num_features + 1):
            coords = np.argwhere(labeled_mask == cluster_id)
            pixel_count = len(coords)

            # Filter out tiny noise clusters
            if pixel_count < self.min_pixels:
                continue

            min_r, min_c = coords.min(axis=0)
            max_r, max_c = coords.max(axis=0)

            # Centroid in pixel space
            cr, cc = coords.mean(axis=0)

            # Transform pixel to geospatial (EPSG:4326)
            # Note: row 0 is max_lat (top), row H is min_lat (bottom)
            geo_min_lon = min_lon + (min_c * lon_step)
            geo_max_lon = min_lon + ((max_c + 1) * lon_step)
            geo_max_lat = max_lat - (min_r * lat_step)
            geo_min_lat = max_lat - ((max_r + 1) * lat_step)

            centroid_lon = min_lon + (cc * lon_step)
            centroid_lat = max_lat - (cr * lat_step)

            # Average confidence inside cluster
            cluster_probs = prob_map[coords[:, 0], coords[:, 1]]
            mean_conf = float(np.mean(cluster_probs))

            cluster = AnomalyCluster(
                cluster_id=cluster_id,
                pixel_bbox=(int(min_r), int(min_c), int(max_r), int(max_c)),
                pixel_centroid=(float(cr), float(cc)),
                geo_bbox=[float(geo_min_lon), float(geo_min_lat), float(geo_max_lon), float(geo_max_lat)],
                geo_centroid=[float(centroid_lon), float(centroid_lat)],
                pixel_count=pixel_count,
                mean_confidence=mean_conf
            )
            clusters.append(cluster)

        logger.info("Cluster extraction concluded", retained_clusters=len(clusters))
        return clusters

    def crop_image_chip(
        self,
        full_raster: np.ndarray,
        cluster: AnomalyCluster,
        padding: int = 16
    ) -> Tuple[np.ndarray, Tuple[int, int]]:
        """Crop an image chip centered around the cluster for secondary classification.

        Args:
            full_raster: (C, H, W) or (H, W) raster array.
            cluster: The target anomaly cluster.
            padding: Additional context pixels around bounding box.

        Returns:
            Tuple of (cropped_chip, (offset_row, offset_col)).
        """
        _, h, w = full_raster.shape if full_raster.ndim == 3 else (1, *full_raster.shape)
        min_r, min_c, max_r, max_c = cluster.pixel_bbox

        padded_min_r = max(0, min_r - padding)
        padded_min_c = max(0, min_c - padding)
        padded_max_r = min(h, max_r + padding)
        padded_max_c = min(w, max_c + padding)

        if full_raster.ndim == 3:
            chip = full_raster[:, padded_min_r:padded_max_r, padded_min_c:padded_max_c]
        else:
            chip = full_raster[padded_min_r:padded_max_r, padded_min_c:padded_max_c]

        return chip, (padded_min_r, padded_min_c)
