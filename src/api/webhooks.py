"""Tactical Webhook Dispatcher for Project Caelum-EO.

Dispatches real-time JSON security alert payloads to configured downstream military SIEMs,
tactical message hubs, or chat webhooks (Slack/Teams/Discord) whenever a detection exceeds
the high-priority threshold (priority_score > 0.85).
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_WEBHOOK_URLS = os.getenv("WEBHOOK_URLS", "")
PRIORITY_ALERT_THRESHOLD = float(os.getenv("PRIORITY_ALERT_THRESHOLD", "0.85"))


def get_configured_webhook_urls() -> List[str]:
    """Parse comma-separated webhook URLs from environment configuration."""
    raw = os.getenv("WEBHOOK_URLS", DEFAULT_WEBHOOK_URLS)
    if not raw.strip():
        return []
    return [url.strip() for url in raw.split(",") if url.strip()]


def build_geoint_alert_payload(detection: Dict[str, Any]) -> Dict[str, Any]:
    """Format standardized defense SIEM security alert payload."""
    score = float(detection.get("priority_score", 0.0))
    severity = "CRITICAL" if score >= 0.90 else "HIGH"

    return {
        "event_type": "HIGH_PRIORITY_GEOINT_DETECTION",
        "severity": severity,
        "detection_id": str(detection.get("id", "")),
        "classification": detection.get("classification", "UNKNOWN_STRUCTURE"),
        "confidence": float(detection.get("confidence", 0.0)),
        "priority_score": score,
        "zone_id": detection.get("zone_id", "UNASSIGNED_ZONE"),
        "area_sq_meters": detection.get("area_sq_meters"),
        "sensor_source": detection.get("sensor_source", "Sentinel-2"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": (
            f"[{severity} ALERT] P-{int(score * 100)} {detection.get('classification')} "
            f"detected in sector {detection.get('zone_id', 'UNASSIGNED')}"
        ),
        "system": {
            "source": "caelum-eo-pipeline",
            "version": "1.0.0",
            "repo": "github.com/FranekJemiolo/Caelum-EO",
        },
    }


def dispatch_high_priority_alert(
    detection: Dict[str, Any],
    webhook_urls: Optional[List[str]] = None,
    timeout_sec: float = 3.0,
) -> List[Dict[str, Any]]:
    """Evaluate detection priority and dispatch JSON payloads to registered webhooks.

    Only triggers if priority_score > 0.85.
    Returns status report for each target webhook URL.
    """
    priority = float(detection.get("priority_score", 0.0))
    if priority <= PRIORITY_ALERT_THRESHOLD:
        logger.debug(
            "Detection below alert threshold, skipping webhook dispatch",
            detection_id=detection.get("id"),
            priority=priority,
            threshold=PRIORITY_ALERT_THRESHOLD,
        )
        return []

    targets = webhook_urls if webhook_urls is not None else get_configured_webhook_urls()
    if not targets:
        logger.info(
            "High priority detection detected but no webhook targets configured",
            detection_id=detection.get("id"),
            priority=priority,
        )
        return []

    payload = build_geoint_alert_payload(detection)
    results: List[Dict[str, Any]] = []

    for url in targets:
        try:
            res = requests.post(url, json=payload, timeout=timeout_sec)
            success = 200 <= res.status_code < 300
            results.append(
                {
                    "url": url,
                    "status": "success" if success else "failed",
                    "status_code": res.status_code,
                }
            )
            logger.info(
                "Webhook dispatch executed",
                url=url,
                status_code=res.status_code,
                detection_id=detection.get("id"),
            )
        except Exception as e:
            results.append(
                {
                    "url": url,
                    "status": "error",
                    "error": str(e),
                }
            )
            logger.error("Webhook dispatch failed", url=url, error=str(e))

    return results
