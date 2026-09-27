"""Inference configuration and model hyperparameters.

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from typing import List, Tuple
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseSettings):
    """Configuration for Prithvi-EO foundation model, YOLOv8-OBB, and GeoSAM."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Device selection (cuda, mps, or cpu)
    device: str = "cpu"

    # Stage 1: Prithvi-EO-2.0 Settings
    prithvi_model_id: str = "ibm-nasa-geospatial/Prithvi-EO-2.0-300M"
    prithvi_weights_path: str = "weights/prithvi_eo_2_0_300m_change_detection.pt"
    # Band order: Blue, Green, Red, Narrow NIR, SWIR 1, SWIR 2
    prithvi_bands: List[str] = ["B02", "B03", "B04", "B8A", "B11", "B12"]
    # Empirical means and standard deviations for Copernicus Sentinel-2 Level-2A
    prithvi_means: List[float] = [0.134, 0.141, 0.158, 0.285, 0.178, 0.126]
    prithvi_stds: List[float] = [0.082, 0.076, 0.088, 0.124, 0.091, 0.078]
    change_probability_threshold: float = 0.60
    min_cluster_pixels: int = 20

    # Stage 2a: YOLOv8-OBB Infrastructure Classifier
    yolo_model_path: str = "weights/yolov8_obb_geoint.pt"
    yolo_conf_threshold: float = 0.45
    yolo_target_classes: List[str] = [
        "Logistics_Depot",
        "Radar_Dome",
        "Airfield_Runway",
        "SAM_Battery_Site",
        "Hardened_Shelter",
        "Naval_Pier_Berth",
        "Fuel_Storage_Tank",
        "Vehicle_Staging_Area"
    ]

    # Stage 2b: GeoSAM Segmenter
    geosam_model_type: str = "vit_h"
    geosam_checkpoint_path: str = "weights/sam_vit_h_4b8939.pth"
    polygon_simplification_tolerance: float = 0.00002  # Degrees (~2 meters)


inference_settings = ModelSettings()
