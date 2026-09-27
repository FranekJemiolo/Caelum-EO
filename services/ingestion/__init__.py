"""STAC Ingestion Firehose Package for Project Caelum-EO."""

from services.ingestion.cdse_stac_client import CDSEStacClient
from services.ingestion.config import Geofence, IngestionConfig, STACItemPayload
from services.ingestion.kafka_producer import GEOINTKafkaProducer
from services.ingestion.poll_worker import STACIngestionWorker

__all__ = [
    "IngestionConfig",
    "STACItemPayload",
    "Geofence",
    "CDSEStacClient",
    "GEOINTKafkaProducer",
    "STACIngestionWorker",
]
