"""ETL and raster processing package for Project Caelum-EO."""

from src.etl.cdse_client import CDSEClient, STACBandMeta, STACItemPayload
from src.etl.raster_processor import RasterAlignmentProcessor
from src.etl.storage import ObjectStorageManager, storage

__all__ = [
    "ObjectStorageManager",
    "storage",
    "CDSEClient",
    "STACItemPayload",
    "STACBandMeta",
    "RasterAlignmentProcessor",
]
