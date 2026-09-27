# Project Caelum-EO: Data Model & PostGIS Schema Specification

**Repository Namespace:** `github.com/FranekJemiolo/Caelum-EO`  
**Database Engine:** PostgreSQL 15+ with PostGIS 3.3+  
**Migration Path:** `src/db/init.sql`

---

## 1. Schema Definition & Entity Relational Design

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Domain Classification Enum
CREATE TYPE infrastructure_class AS ENUM (
    'LOGISTICS_DEPOT',
    'RUNWAY_TAXIWAY',
    'RADAR_DOME',
    'DEFENSE_REVETMENT',
    'INDUSTRIAL_BUILDING',
    'UNKNOWN_STRUCTURE'
);

-- Primary Vector Intelligence Table
CREATE TABLE IF NOT EXISTS infrastructure_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    geometry GEOMETRY(Polygon, 4326) NOT NULL,
    classification infrastructure_class NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    area_sq_meters DOUBLE PRECISION GENERATED ALWAYS AS (ST_Area(geometry::geography)) STORED,
    baseline_timestamp TIMESTAMPTZ NOT NULL,
    detection_timestamp TIMESTAMPTZ NOT NULL,
    sensor_source VARCHAR(64) NOT NULL,
    raw_chip_s3_uri VARCHAR(512),
    stac_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Spatial GIST Index on Geometry
CREATE INDEX IF NOT EXISTS idx_infra_detections_geom 
    ON infrastructure_detections USING GIST (geometry);

-- Temporal Descending Index for Timeline Scrubber Queries
CREATE INDEX IF NOT EXISTS idx_infra_detections_timestamp 
    ON infrastructure_detections (detection_timestamp DESC);

-- Categorical Index for Layer Toggles
CREATE INDEX IF NOT EXISTS idx_infra_detections_class 
    ON infrastructure_detections (classification);
```

---

## 2. Field Specifications

| Column Name | Data Type | Nullable | Description | Example |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | Globally unique detection identifier (v4) | `a1b2c3d4-e5f6-47a8-b901-23456789abcd` |
| `geometry` | `GEOMETRY(Polygon, 4326)` | No | Vectorized polygon perimeter in WGS 84 coordinate reference system | `POLYGON((23.15 54.12, ...))` |
| `classification` | `infrastructure_class` | No | Tactical categorization tag | `'LOGISTICS_DEPOT'`, `'RADAR_DOME'` |
| `confidence` | `REAL` | No | Composite confidence score ($0.0 \le c \le 1.0$) | `0.942` |
| `area_sq_meters` | `DOUBLE PRECISION` | No | Generated on insertion: geodesic surface area in $m^2$ via PostGIS geography | `12450.75` |
| `baseline_timestamp` | `TIMESTAMPTZ` | No | Time of reference observation $T_0$ (UTC) | `2026-05-15T08:30:00Z` |
| `detection_timestamp` | `TIMESTAMPTZ` | No | Time of change detection observation $T_1$ (UTC) | `2026-09-27T10:00:31Z` |
| `sensor_source` | `VARCHAR(64)` | No | Spaceborne sensor identification | `'Sentinel-2A-MSI-L2A'` |
| `raw_chip_s3_uri` | `VARCHAR(512)` | Yes | URI to visual verification chip in MinIO / S3 | `s3://caelum-chips/.../chip_rgb.png` |
| `stac_metadata` | `JSONB` | No | Raw Copernicus STAC provenance payload | `{"item_id": "S2A_MSIL2A_...", ...}` |
| `created_at` | `TIMESTAMPTZ` | No | Database transaction commit time | `2026-09-27T21:55:00Z` |
