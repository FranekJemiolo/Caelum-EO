# Database Schema & Spatial Indexing Specification

**Repository:** `github.com/FranekJemiolo/Caelum-EO`  
**Database:** PostgreSQL 16 with PostGIS 3.4

---

## 1. Schema Definition

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

CREATE TABLE infrastructure_detections (
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

## 2. Spatial & Temporal Indexes

1. **Spatial GIST Index:**
   ```sql
   CREATE INDEX idx_infra_detections_geometry 
   ON infrastructure_detections USING GIST (geometry);
   ```
   Enables sub-10ms bounding box queries (`ST_Intersects`, `ST_Contains`) as the analyst pans and zooms across map tiles in Deck.gl.

2. **Temporal B-Tree Index:**
   ```sql
   CREATE INDEX idx_infra_detections_date 
   ON infrastructure_detections (detection_date);
   ```
   Accelerates queries issued by the Deck.gl timeline scrubber during playback.

3. **Composite Covering Index:**
   ```sql
   CREATE INDEX idx_infra_detections_date_geom
   ON infrastructure_detections USING GIST (geometry)
   INCLUDE (detection_date, classification, confidence);
   ```
   Provides index-only scans for tile bounding boxes filtered by active classifications and date windows.
