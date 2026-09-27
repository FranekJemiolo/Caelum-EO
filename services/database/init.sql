-- Project Caelum-EO: Spatial Database Schema
-- Target: PostgreSQL 16 with PostGIS 3.4
-- Namespace: github.com/FranekJemiolo/Caelum-EO

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- Classification Enum
DO $$ BEGIN
    CREATE TYPE infrastructure_type AS ENUM (
        'Logistics_Depot',
        'Radar_Dome',
        'Airfield_Runway',
        'SAM_Battery_Site',
        'Hardened_Shelter',
        'Naval_Pier_Berth',
        'Fuel_Storage_Tank',
        'Vehicle_Staging_Area'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Primary spatial detection table
CREATE TABLE IF NOT EXISTS infrastructure_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    geometry GEOMETRY(Polygon, 4326) NOT NULL,
    classification VARCHAR(64) NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    detection_date TIMESTAMPTZ NOT NULL,
    source_imagery JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Spatial GIST Index for bounding box tile lookups
CREATE INDEX IF NOT EXISTS idx_infra_detections_geometry 
    ON infrastructure_detections USING GIST (geometry);

-- Temporal B-Tree Index for scrubber range filtering
CREATE INDEX IF NOT EXISTS idx_infra_detections_date 
    ON infrastructure_detections (detection_date);

-- Categorical Index for layer visibility filtering
CREATE INDEX IF NOT EXISTS idx_infra_detections_classification 
    ON infrastructure_detections (classification);

-- Multi-column composite index for optimized spatial-temporal queries
CREATE INDEX IF NOT EXISTS idx_infra_detections_date_geom
    ON infrastructure_detections USING GIST (geometry)
    INCLUDE (detection_date, classification, confidence);

-- Seed Initial Strategic GEOINT Intelligence (Suwalki Gap & Strategic Zones)
INSERT INTO infrastructure_detections (id, geometry, classification, confidence, detection_date, source_imagery)
VALUES 
    (
        'a1b2c3d4-e5f6-47a8-b901-23456789abcd',
        ST_GeomFromText('POLYGON((23.1500 54.1200, 23.1550 54.1200, 23.1550 54.1250, 23.1500 54.1250, 23.1500 54.1200))', 4326),
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
        ST_GeomFromText('POLYGON((23.3000 54.2000, 23.3600 54.2050, 23.3550 54.2150, 23.2950 54.2100, 23.3000 54.2000))', 4326),
        'Airfield_Runway',
        0.984,
        '2026-07-10 14:00:00+00',
        '{"item_id": "S2A_MSIL2A_20260710_T34UFB", "platform": "sentinel-2a", "cloud_cover": 1.2}'::jsonb
    ),
    (
        'd4e5f6a7-b8c9-40d1-e234-56789abcdef0',
        ST_GeomFromText('POLYGON((23.2200 54.1300, 23.2350 54.1300, 23.2350 54.1420, 23.2200 54.1420, 23.2200 54.1300))', 4326),
        'SAM_Battery_Site',
        0.941,
        '2026-08-22 09:45:00+00',
        '{"item_id": "S2B_MSIL2A_20260822_T34UFB", "platform": "sentinel-2b", "cloud_cover": 0.8}'::jsonb
    ),
    (
        'e5f6a7b8-c9d0-41e2-f345-6789abcdef01',
        ST_GeomFromText('POLYGON((23.1900 54.1180, 23.2050 54.1180, 23.2050 54.1280, 23.1900 54.1280, 23.1900 54.1180))', 4326),
        'Hardened_Shelter',
        0.893,
        '2026-09-18 10:20:00+00',
        '{"item_id": "S2A_MSIL2A_20260918_T34UFB", "platform": "sentinel-2a", "cloud_cover": 3.4}'::jsonb
    )
ON CONFLICT (id) DO NOTHING;
