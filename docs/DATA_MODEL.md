# Project Caelum-EO: Data Model & PostGIS Schema Specification

**Repository Namespace:** `github.com/FranekJemiolo/Caelum-EO`  
**Database Engine:** PostgreSQL 15 with PostGIS 3.3  
**Migration Path:** `src/db/init.sql`

---

## 1. Relational & Spatial Entity: `infrastructure_detections`

The primary storage entity captures vectorized structures detected through satellite change inference. Every entry is indexed spatially to support sub-10ms WebGL viewport queries.

### Table Definition
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

CREATE TABLE IF NOT EXISTS infrastructure_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    geometry GEOMETRY(Polygon, 4326) NOT NULL,
    classification VARCHAR(64) NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    detection_date TIMESTAMPTZ NOT NULL,
    source_imagery JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 2. Field Specifications

| Column Name | Data Type | Nullable | Description | Example |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | Unique detection identifier (v4) | `a1b2c3d4-e5f6-47a8-b901-23456789abcd` |
| `geometry` | `GEOMETRY(Polygon, 4326)` | No | Physical perimeter polygon in WGS 84 coordinate reference system | `POLYGON((23.15 54.12, 23.16 54.12, ...))` |
| `classification` | `VARCHAR(64)` | No | Target infrastructure categorization label | `Logistics_Depot`, `Radar_Dome`, `Airfield_Runway` |
| `confidence` | `REAL` | No | Composite model confidence score (0.0 to 1.0) | `0.9450` |
| `detection_date` | `TIMESTAMPTZ` | No | Observation acquisition timestamp (UTC) of newly acquired scene | `2026-09-27T10:00:31Z` |
| `source_imagery` | `JSONB` | No | Raw Copernicus STAC metadata payload, band URLs, sensor ID, cloud cover | `{"item_id": "S2A_MSIL2A_...", "cloud_cover": 3.4}` |
| `created_at` | `TIMESTAMPTZ` | No | Database insertion timestamp (system clock) | `2026-09-27T21:55:00Z` |

---

## 3. Spatial & Temporal Indexes

1. **Spatial Bounding Index (`GIST`):**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_infra_detections_geometry 
       ON infrastructure_detections USING GIST (geometry);
   ```
   Accelerates bounding box queries (`ST_Intersects`, `ST_Contains`, `&&`) executed by Deck.gl viewport frustum queries.

2. **Temporal B-Tree Index:**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_infra_detections_date 
       ON infrastructure_detections (detection_date);
   ```
   Enables high-speed range queries when scrubbing the timeline slider.

3. **Categorical Index:**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_infra_detections_class 
       ON infrastructure_detections (classification);
   ```
   Allows dynamic category filtering without table scans.

4. **Composite Index for Analytics:**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_infra_detections_date_geom
       ON infrastructure_detections USING GIST (geometry)
       INCLUDE (detection_date, classification, confidence);
   ```
   Enables index-only scans for tile bounding boxes filtered by active classifications and date windows.
