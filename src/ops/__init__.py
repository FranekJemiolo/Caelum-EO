"""Caelum-EO Operations, Observability & Fault-Tolerance Package."""

from src.ops.dlq import DeadLetterQueue, dlq_manager
from src.ops.metrics import (
    DLQ_MESSAGES_TOTAL,
    GPU_MEMORY_UTILIZATION_PERCENT,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    INFERENCE_TILES_PROCESSED_TOTAL,
    KAFKA_QUEUE_LAG,
    MINIO_DISK_SPACE_REMAINING_BYTES,
    generate_metrics_payload,
    update_system_gauges,
)

__all__ = [
    "DeadLetterQueue",
    "dlq_manager",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    "KAFKA_QUEUE_LAG",
    "INFERENCE_TILES_PROCESSED_TOTAL",
    "DLQ_MESSAGES_TOTAL",
    "GPU_MEMORY_UTILIZATION_PERCENT",
    "MINIO_DISK_SPACE_REMAINING_BYTES",
    "generate_metrics_payload",
    "update_system_gauges",
]
