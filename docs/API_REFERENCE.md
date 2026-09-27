# Project Caelum-EO: API Reference & OpenAPI Specification

**Base URL:** `http://localhost:8000/api/v1`
**OpenAPI Interactive Documentation:** `http://localhost:8000/docs`
**Repository:** `github.com/FranekJemiolo/Caelum-EO`

---

## 1. Endpoints Overview

| Method  | Endpoint                           | Description                                                   |
| ------- | ---------------------------------- | ------------------------------------------------------------- |
| `GET`   | `/health`                          | System liveness probe & platform status                       |
| `GET`   | `/detections`                      | Query detection vectors as GeoJSON FeatureCollection          |
| `GET`   | `/zones/summary`                   | Spatial JOIN aggregated metrics grouped by geographic zone    |
| `GET`   | `/triage/queue`                    | Pending review detections ranked by descending priority score |
| `GET`   | `/detections/{id}/imagery`         | Image chip URLs and sensor metadata for inspection            |
| `GET`   | `/detections/{id}/imagery/{layer}` | Stream binary PNG chips (`t0`, `t1`, `mask`)                  |
| `PATCH` | `/detections/{id}/review`          | Submit Human-in-the-Loop review & log audit trail             |

---

## 2. Endpoint Details

### 2.1 Detection Exploration

`GET /api/v1/detections`

**Query Parameters:**

- `classification` (string, optional): Filter by `infrastructure_class` enum.
- `review_status` (string, optional): Filter by `PENDING_REVIEW`, `VERIFIED`, `MISCLASSIFIED`, `FALSE_POSITIVE`.
- `min_confidence` (float, optional, default: 0.0): Filter by minimum confidence score.
- `start_date` (string, optional): ISO timestamp lower bound.
- `end_date` (string, optional): ISO timestamp upper bound.
- `zone_id` (string, optional): Filter detections within a specific zone.
- `limit` (int, default: 100): Maximum features to return.
- `offset` (int, default: 0): Pagination offset.

**Response (200 OK):**

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [23.148, 54.118],
            [23.156, 54.118],
            [23.156, 54.126],
            [23.148, 54.126],
            [23.148, 54.118]
          ]
        ]
      },
      "properties": {
        "classification": "RADAR_DOME",
        "confidence": 0.965,
        "area_sq_meters": 3450.0,
        "baseline_timestamp": "2026-05-15T08:30:00Z",
        "detection_timestamp": "2026-05-15T08:30:00Z",
        "sensor_source": "Sentinel-2A-MSI-L2A",
        "zone_id": "ZONE-SUWALKI-CORRIDOR",
        "review_status": "PENDING_REVIEW",
        "priority_score": 0.95
      }
    }
  ]
}
```

---

### 2.2 Zone Count Aggregations

`GET /api/v1/zones/summary`

Performs a spatial JOIN between `geographic_zones` and `infrastructure_detections`.

**Response (200 OK):**

```json
[
  {
    "id": "ZONE-SUWALKI-CORRIDOR",
    "name": "Suwalki Gap Strategic Corridor",
    "alert_level": "HIGH",
    "boundary": {
      "type": "Polygon",
      "coordinates": [
        [
          [23.0, 54.0],
          [23.5, 54.0],
          [23.5, 54.4],
          [23.0, 54.4],
          [23.0, 54.0]
        ]
      ]
    },
    "total_detections": 5,
    "new_detections_24h": 2,
    "new_detections_7d": 5,
    "high_priority_count": 3,
    "classification_breakdown": {
      "RADAR_DOME": 1,
      "RUNWAY_TAXIWAY": 1,
      "LOGISTICS_DEPOT": 1,
      "DEFENSE_REVETMENT": 1,
      "INDUSTRIAL_BUILDING": 1
    }
  }
]
```

---

### 2.3 High-Priority Triage Queue

`GET /api/v1/triage/queue?limit=50`

Returns anomalies with `review_status = 'PENDING_REVIEW'` ordered by `priority_score DESC`.

**Priority Score Formula:**
$$\text{Priority} = 0.40 \times \text{Severity} + 0.35 \times \text{ZoneAlert} + 0.25 \times \text{Confidence}$$

---

### 2.4 Multi-Temporal Image Chip Retrieval

`GET /api/v1/detections/{id}/imagery`

**Response (200 OK):**

```json
{
  "detection_id": "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
  "t0_image_url": "/api/v1/detections/a1b2c3d4-e5f6-47a8-b901-23456789abcd/imagery/t0",
  "t1_image_url": "/api/v1/detections/a1b2c3d4-e5f6-47a8-b901-23456789abcd/imagery/t1",
  "mask_image_url": "/api/v1/detections/a1b2c3d4-e5f6-47a8-b901-23456789abcd/imagery/mask",
  "sensor_source": "Sentinel-2A-MSI-L2A",
  "baseline_timestamp": "2026-05-15T08:30:00Z",
  "detection_timestamp": "2026-05-15T08:30:00Z",
  "stac_metadata": { "cloud_cover": 2.1 }
}
```

`GET /api/v1/detections/{id}/imagery/{layer_type}`
Streams high-resolution binary PNG (`image/png`) where `layer_type` is `t0`, `t1`, or `mask`.

---

### 2.5 Human-in-the-Loop Reclassification

`PATCH /api/v1/detections/{id}/review`

**Request Body:**

```json
{
  "review_status": "VERIFIED",
  "verified_class": "RUNWAY_TAXIWAY",
  "reviewer_notes": "Ground verification confirms concrete runway extension.",
  "reviewed_by": "analyst_viper_01"
}
```

**Response (200 OK):**

```json
{
  "id": "c3d4e5f6-a7b8-49c0-d123-456789abcdef",
  "review_status": "VERIFIED",
  "verified_class": "RUNWAY_TAXIWAY",
  "priority_score": 0.1,
  "reviewer_notes": "Ground verification confirms concrete runway extension.",
  "reviewed_by": "analyst_viper_01",
  "reviewed_at": "2026-09-27T22:20:00Z",
  "message": "Detection review committed successfully and audit trail logged."
}
```

Updates `infrastructure_detections` and appends an entry to `review_audit_log`.
