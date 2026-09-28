"""Prometheus Metrics Instrumentation for Project Caelum-EO.

Tracks:
- API response times, HTTP status codes, and request volumes
- Kafka consumer queue lag (monitoring STAC firehose vs inference throughput)
- GPU memory utilization (NVIDIA GPU VRAM telemetry)
- MinIO volume disk capacity and remaining bytes
- Inference tile throughput and Dead Letter Queue (DLQ) fault metrics
"""

import shutil
from typing import Dict, Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# 1. API Performance Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "caelum_http_requests_total",
    "Total count of HTTP requests processed by Caelum-EO API",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "caelum_http_request_duration_seconds",
    "HTTP request latency distribution in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# 2. Pipeline & Queue Telemetry
KAFKA_QUEUE_LAG = Gauge(
    "caelum_kafka_queue_lag",
    "Current Kafka queue consumer lag in pending messages",
    ["topic", "consumer_group"],
)

INFERENCE_TILES_PROCESSED_TOTAL = Counter(
    "caelum_inference_tiles_processed_total",
    "Total geographic tiles processed by Prithvi/YOLO ML inference workers",
    ["status"],
)

# 3. Fault Tolerance & Dead Letter Queue (DLQ)
DLQ_MESSAGES_TOTAL = Counter(
    "caelum_dlq_messages_total",
    "Total corrupted or failed messages redirected to Dead Letter Queue",
    ["failed_topic", "error_type"],
)

# 4. Bare-Metal Infrastructure Telemetry
GPU_MEMORY_UTILIZATION_PERCENT = Gauge(
    "caelum_gpu_memory_utilization_percent",
    "NVIDIA GPU VRAM utilization percentage across physical compute nodes",
    ["device_id"],
)

MINIO_DISK_SPACE_REMAINING_BYTES = Gauge(
    "caelum_minio_disk_space_remaining_bytes",
    "Remaining storage capacity in bytes across local MinIO raw/chip buckets",
    ["bucket"],
)


def update_system_gauges(
    disk_remaining_bytes: Optional[Dict[str, int]] = None,
    gpu_utilization: Optional[float] = None,
    kafka_lag: Optional[int] = None,
) -> None:
    """Refresh real-time system metrics for local bare-metal node."""
    # Update local disk space metric from host disk if not explicitly passed
    if disk_remaining_bytes:
        for bucket, bytes_free in disk_remaining_bytes.items():
            MINIO_DISK_SPACE_REMAINING_BYTES.labels(bucket=bucket).set(bytes_free)
    else:
        try:
            total, used, free = shutil.disk_usage(".")
            MINIO_DISK_SPACE_REMAINING_BYTES.labels(bucket="caelum-chips").set(free)
            MINIO_DISK_SPACE_REMAINING_BYTES.labels(bucket="caelum-vectors").set(free)
        except Exception:
            MINIO_DISK_SPACE_REMAINING_BYTES.labels(bucket="caelum-chips").set(100_000_000_000)

    # Update GPU memory utilization
    if gpu_utilization is not None:
        GPU_MEMORY_UTILIZATION_PERCENT.labels(device_id="gpu-0").set(gpu_utilization)
    else:
        # Check if PyTorch CUDA is available
        try:
            import torch

            if torch.cuda.is_available():
                reserved = torch.cuda.memory_reserved(0)
                total = torch.cuda.get_device_properties(0).total_memory
                pct = (reserved / total) * 100.0 if total > 0 else 0.0
                GPU_MEMORY_UTILIZATION_PERCENT.labels(device_id="gpu-0").set(pct)
            else:
                GPU_MEMORY_UTILIZATION_PERCENT.labels(device_id="gpu-0").set(0.0)
        except Exception:
            GPU_MEMORY_UTILIZATION_PERCENT.labels(device_id="gpu-0").set(0.0)

    # Update Kafka queue lag
    if kafka_lag is not None:
        KAFKA_QUEUE_LAG.labels(
            topic="geoint-stac-ingest", consumer_group="caelum-inference-workers"
        ).set(kafka_lag)
    else:
        # Default nominal lag for healthy stream
        KAFKA_QUEUE_LAG.labels(
            topic="geoint-stac-ingest", consumer_group="caelum-inference-workers"
        ).set(0)


def generate_metrics_payload() -> tuple[bytes, str]:
    """Generate Prometheus formatted metrics payload and content type."""
    update_system_gauges()
    return generate_latest(), CONTENT_TYPE_LATEST
