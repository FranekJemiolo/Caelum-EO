-- Project Caelum-EO: PostGIS 3.3 Database Migration Script
-- Mounted into Docker container at /docker-entrypoint-initdb.d/init.sql
-- Repository: github.com/FranekJemiolo/Caelum-EO

-- 1. Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- 2. Primary Vector Intelligence Table
CREATE TABLE IF NOT EXISTS infrastructure_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    geometry GEOMETRY(Polygon, 4326) NOT NULL,
    classification VARCHAR(64) NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    detection_date TIMESTAMPTZ NOT NULL,
    source_imagery JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Explicit Spatial Index (GIST) on Geometry
CREATE INDEX IF NOT EXISTS idx_infra_detections_geometry 
    ON infrastructure_detections USING GIST (geometry);

-- 4. Temporal Index for Timeline Scrubber Queries
CREATE INDEX IF NOT EXISTS idx_infra_detections_date 
    ON infrastructure_detections (detection_date);

-- 5. Categorical Index for Layer Toggles
CREATE INDEX IF NOT EXISTS idx_infra_detections_class 
    ON infrastructure_detections (classification);

-- 6. Covering Spatial Index for Viewport Tile Queries
CREATE INDEX IF NOT EXISTS idx_infra_detections_date_geom
    ON infrastructure_detections USING GIST (geometry)
    INCLUDE (detection_date, classification, confidence);

-- 7. Seed Initial Operational GEOINT Detections (Suwalki Strategic Corridor)
INSERT INTO infrastructure_detections (id, geometry, classification, confidence, detection_date, source_imagery)
VALUES 
    (
        'a1b2c3d4-e5f6-47a8-b901-23456789abcd',
        ST_GeomFromText('POLYGON((23.1480 54.1180, 23.1560 54.1180, 23.1560 54.1260, 23.1480 54.1260, 23.1480 54.1180))', 4326),
        'Radar_Dome',
        0.965,
        '2026-05-15 08:30:00+00',
        '{"item_id": "S2A_MSIL2A_20260515_T34UFB", "platform": "sentinel-2a", "cloud_cover": 2.1}'::jsonb
    ),
    (
        'b2c3d4e5-f6a7-48b9-c012-3456789abcde',
        ST_GeomFromText('POLYGON((23.1800 54.1000, 23.2100 54.1000, 23.2100 54.1150, 23.1800 54.1150, 23.1800 54.1000))', 4326),
        'Logistics_Depot',
        0.912,
        '2026-06-02 11:15:00+00',
        '{"item_id": "S2B_MSIL2A_20260602_T34UFB", "platform": "sentinel-2b", "cloud_cover": 4.5}'::jsonb
    ),
    (
        'c3d4e5f6-a7b8-49c0-d123-456789abcdef',
        ST_GeomFromText('POLYGON((23.2800 54.1950, 23.3550 54.2000, 23.3500 54.2150, 23.2750 54.2100, 23.2800 54.1950))', 4326),
        'Airfield_Runway',
        0.984,
        '2026-07-10 14:00:00+00',
        '{"item_id": "S2A_MSIL2A_20260710_T34UFB", "platform": "sentinel-2a", "cloud_cover": 1.2}'::jsonb
    ),
    (
        'd4e5f6a7-b8c9-40d1-e234-56789abcdef0',
        ST_GeomFromText('POLYGON((23.2200 54.1300, 23.2380 54.1300, 23.2380 54.1440, 23.2200 54.1440, 23.2200 54.1300))', 4326),
        'SAM_Battery_Site',
        0.941,
        '2026-08-22 09:45:00+00',
        '{"item_id": "S2B_MSIL2A_20260822_T34UFB", "platform": "sentinel-2b", "cloud_cover": 0.8}'::jsonb
    ),
    (
        'e5f6a7b8-c9d0-41e2-f345-6789abcdef01',
        ST_GeomFromText('POLYGON((23.1900 54.1180, 23.2080 54.1180, 23.2080 54.1290, 23.1900 54.1290, 23.1900 54.1180))', 4326),
        'Hardened_Shelter',
        0.893,
        '2026-09-18 10:20:00+00',
        '{"item_id": "S2A_MSIL2A_20260918_T34UFB", "platform": "sentinel-2a", "cloud_cover": 3.4}'::jsonb
    )
ON CONFLICT (id) DO NOTHING;
