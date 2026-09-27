"""MinIO / AWS S3 Object Storage Abstraction for Project Caelum-EO.

Manages data lifecycle across the three core operational buckets:
- caelum-raw: Downloaded or cached windowed GeoTIFF bands
- caelum-interim: Normalized multi-temporal tensor stacks (.npy)
- caelum-chips: High-resolution visual verification chips for analysts

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

import io
import os
from pathlib import Path
from typing import List, Optional
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# S3 / MinIO Configuration
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
S3_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")
S3_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

REQUIRED_BUCKETS = ["caelum-raw", "caelum-interim", "caelum-chips"]


class ObjectStorageManager:
    """Manages S3 / MinIO buckets, streaming uploads, and tensor persistence."""

    def __init__(
        self,
        endpoint_url: str = S3_ENDPOINT,
        access_key: str = S3_ACCESS_KEY,
        secret_key: str = S3_SECRET_KEY,
        region: str = S3_REGION,
        fallback_local_dir: str = "./data/minio_storage"
    ):
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.fallback_local_dir = Path(fallback_local_dir)
        self.fallback_mode = False
        self._s3_client = None

        self._init_connection()

    def _init_connection(self):
        """Initialize S3 client and ensure required buckets exist, with local fallback."""
        try:
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=Config(signature_version="s3v4", connect_timeout=3, retries={"max_attempts": 2})
            )
            # Healthcheck connection by listing buckets
            self._s3_client.list_buckets()
            self._ensure_buckets()
            logger.info("Connected to MinIO/S3 object store", endpoint=self.endpoint_url)
        except Exception as exc:
            logger.warning(
                "MinIO/S3 unavailable; switching to resilient local filesystem object store",
                fallback_path=str(self.fallback_local_dir),
                error=str(exc)
            )
            self.fallback_mode = True
            for bucket in REQUIRED_BUCKETS:
                (self.fallback_local_dir / bucket).mkdir(parents=True, exist_ok=True)

    def _ensure_buckets(self):
        """Create required buckets if they do not exist."""
        existing = {b["Name"] for b in self._s3_client.list_buckets().get("Buckets", [])}
        for bucket in REQUIRED_BUCKETS:
            if bucket not in existing:
                logger.info("Creating object storage bucket", bucket=bucket)
                try:
                    self._s3_client.create_bucket(Bucket=bucket)
                except ClientError as err:
                    logger.debug("Bucket already exists or handled concurrently", bucket=bucket, error=str(err))

    def upload_bytes(self, bucket: str, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        """Upload raw bytes to object storage."""
        if self.fallback_mode:
            dest = self.fallback_local_dir / bucket / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return f"file://{dest.absolute()}"

        extra_args = {"ContentType": content_type} if content_type else {}
        self._s3_client.put_object(Bucket=bucket, Key=key, Body=data, **extra_args)
        return f"s3://{bucket}/{key}"

    def download_bytes(self, bucket: str, key: str) -> bytes:
        """Download raw bytes from object storage."""
        if self.fallback_mode:
            src = self.fallback_local_dir / bucket / key
            if not src.exists():
                raise FileNotFoundError(f"Key not found in local storage: {bucket}/{key}")
            return src.read_bytes()

        response = self._s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def upload_tensor_array(self, bucket: str, key: str, array: np.ndarray) -> str:
        """Serialize a multi-temporal numpy tensor array to S3/MinIO."""
        buffer = io.BytesIO()
        np.save(buffer, array)
        buffer.seek(0)
        return self.upload_bytes(bucket, key, buffer.getvalue(), content_type="application/x-numpy")

    def download_tensor_array(self, bucket: str, key: str) -> np.ndarray:
        """Download and deserialize a numpy tensor array from S3/MinIO."""
        data_bytes = self.download_bytes(bucket, key)
        buffer = io.BytesIO(data_bytes)
        buffer.seek(0)
        return np.load(buffer)


# Default singleton instance
storage = ObjectStorageManager()
