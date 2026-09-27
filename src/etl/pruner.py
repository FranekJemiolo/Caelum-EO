"""Data Lifecycle & Raw Raster Pruner for Project Caelum-EO.

Scheduled background task that prunes raw satellite GeoTIFF rasters older than
a configurable retention period (default: 7 days) from storage (MinIO/S3 caelum-raw bucket
or local raw directory), preserving high-value cropped anomaly chips and PostGIS vector records.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_RETENTION_DAYS = int(os.getenv("RAW_DATA_RETENTION_DAYS", "7"))
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
RAW_BUCKET_NAME = os.getenv("RAW_BUCKET_NAME", "caelum-raw")


class PruneReport:
    """Detailed summary of the data pruning execution."""

    def __init__(self, retention_days: int, dry_run: bool = False):
        self.retention_days = retention_days
        self.dry_run = dry_run
        self.scanned_count = 0
        self.pruned_count = 0
        self.retained_count = 0
        self.bytes_freed = 0
        self.pruned_files: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "retention_days": self.retention_days,
            "dry_run": self.dry_run,
            "scanned_count": self.scanned_count,
            "pruned_count": self.pruned_count,
            "retained_count": self.retained_count,
            "bytes_freed_mb": round(self.bytes_freed / (1024 * 1024), 2),
            "pruned_files": self.pruned_files,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }


def prune_local_raw_rasters(
    directory: Path,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    dry_run: bool = False,
) -> PruneReport:
    """Prune raster files in local directory older than retention threshold."""
    report = PruneReport(retention_days=retention_days, dry_run=dry_run)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    if not directory.exists():
        logger.info("Local raw raster directory does not exist, skipping", path=str(directory))
        return report

    for item in directory.rglob("*"):
        if item.is_file() and item.suffix.lower() in [".tif", ".tiff", ".jp2", ".tar", ".gz"]:
            report.scanned_count += 1
            mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
            file_size = item.stat().st_size

            if mtime < cutoff:
                report.pruned_count += 1
                report.bytes_freed += file_size
                report.pruned_files.append(str(item))

                if not dry_run:
                    try:
                        item.unlink()
                        logger.info(
                            "Pruned expired raw raster",
                            path=str(item),
                            age_days=(datetime.now(timezone.utc) - mtime).days,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to delete expired raster", path=str(item), error=str(e)
                        )
            else:
                report.retained_count += 1

    return report


def prune_s3_raw_bucket(
    bucket_name: str = RAW_BUCKET_NAME,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    dry_run: bool = False,
) -> Optional[PruneReport]:
    """Prune expired raw objects in MinIO/S3 bucket using boto3 if available."""
    try:
        import boto3
        from botocore.client import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        report = PruneReport(retention_days=retention_days, dry_run=dry_run)

        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                report.scanned_count += 1
                key = obj["Key"]
                last_modified = obj["LastModified"]
                size = obj["Size"]

                if last_modified < cutoff:
                    report.pruned_count += 1
                    report.bytes_freed += size
                    report.pruned_files.append(key)

                    if not dry_run:
                        s3.delete_object(Bucket=bucket_name, Key=key)
                        logger.info("Pruned expired S3 raw raster", key=key, bucket=bucket_name)
                else:
                    report.retained_count += 1

        return report
    except Exception as e:
        logger.warning(
            "Could not connect to S3/MinIO for pruning, falling back to local files", error=str(e)
        )
        return None


def run_pruning_cycle(
    retention_days: int = DEFAULT_RETENTION_DAYS,
    local_raw_dir: str = "data/raw",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute complete data lifecycle pruning cycle across S3 and local storage."""
    logger.info(
        "Starting raw satellite data retention pruning cycle",
        retention_days=retention_days,
        dry_run=dry_run,
    )

    s3_report = prune_s3_raw_bucket(retention_days=retention_days, dry_run=dry_run)
    local_report = prune_local_raw_rasters(
        Path(local_raw_dir), retention_days=retention_days, dry_run=dry_run
    )

    summary = {
        "retention_days": retention_days,
        "dry_run": dry_run,
        "local_storage": local_report.to_dict(),
        "s3_storage": s3_report.to_dict() if s3_report else None,
        "total_pruned_count": local_report.pruned_count
        + (s3_report.pruned_count if s3_report else 0),
        "total_bytes_freed_mb": round(
            (local_report.bytes_freed + (s3_report.bytes_freed if s3_report else 0))
            / (1024 * 1024),
            2,
        ),
    }

    logger.info(
        "Raw data retention pruning cycle finished",
        total_pruned=summary["total_pruned_count"],
        total_mb_freed=summary["total_bytes_freed_mb"],
    )
    return summary


@click.command()
@click.option(
    "--retention-days",
    default=DEFAULT_RETENTION_DAYS,
    help="Retention period in days for raw GeoTIFF imagery",
)
@click.option("--dir", "raw_dir", default="data/raw", help="Local directory containing raw imagery")
@click.option("--dry-run", is_flag=True, help="Scan and report without deleting files")
def main(retention_days: int, raw_dir: str, dry_run: bool) -> None:
    """Run data lifecycle retention pruning job."""
    result = run_pruning_cycle(
        retention_days=retention_days, local_raw_dir=raw_dir, dry_run=dry_run
    )
    click.echo(
        f"Pruning completed: {result['total_pruned_count']} files pruned, {result['total_bytes_freed_mb']} MB freed."
    )


if __name__ == "__main__":
    main()
