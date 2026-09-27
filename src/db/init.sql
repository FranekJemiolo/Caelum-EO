-- Project Caelum-EO: PostGIS Database Initialization Script
-- Mounted into PostGIS 15+ container at /docker-entrypoint-initdb.d/init.sql
-- Repository: github.com/FranekJemiolo/Caelum-EO

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

-- Primary Spatial Intelligence Table
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

-- Seed Initial Strategic Detections for Instant Local Verification
INSERT INTO infrastructure_detections (
    id, geometry, classification, confidence, baseline_timestamp, detection_timestamp, sensor_source, stac_metadata
) VALUES 
    (
        'a1b2c3d4-e5f6-47a8-b901-23456789abcd',
        ST_GeomFromText('POLYGON((23.1480 54.1180, 23.1560 54.1180, 23.1560 54.1260, 23.1480 54.1260, 23.1480 54.1180))', 4326),
        'RADAR_DOME',
        0.965,
        '2026-05-15 08:30:00+00',
        '2026-05-15 08:30:00+00',
        'Sentinel-2A-MSI-L2A',
        '{"item_id": "S2A_MSIL2A_20260515_T34UFB", "cloud_cover": 2.1}'::jsonb
    ),
    (
        'b2c3d4e5-f6a7-48b9-c012-3456789abcde',
        ST_GeomFromText('POLYGON((23.1800 54.1000, 23.2100 54.1000, 23.2100 54.1150, 23.1800 54.1150, 23.1800 54.1000))', 4326),
        'LOGISTICS_DEPOT',
        0.912,
        '2026-05-15 08:30:00+00',
        '2026-06-02 11:15:00+00',
        'Sentinel-2B-MSI-L2A',
        '{"item_id": "S2B_MSIL2A_20260602_T34UFB", "cloud_cover": 4.5}'::jsonb
    ),
    (
        'c3d4e5f6-a7b8-49c0-d123-456789abcdef',
        ST_GeomFromText('POLYGON((23.2800 54.1950, 23.3550 54.2000, 23.3500 54.2150, 23.2750 54.2100, 23.2800 54.1950))', 4326),
        'RUNWAY_TAXIWAY',
        0.984,
        '2026-05-15 08:30:00+00',
        '2026-07-10 14:00:00+00',
        'Sentinel-2A-MSI-L2A',
        '{"item_id": "S2A_MSIL2A_20260710_T34UFB", "cloud_cover": 1.2}'::jsonb
    ),
    (
        'd4e5f6a7-b8c9-40d1-e234-56789abcdef0',
        ST_GeomFromText('POLYGON((23.2200 54.1300, 23.2380 54.1300, 23.2380 54.1440, 23.2200 54.1440, 23.2200 54.1300))', 4326),
        'DEFENSE_REVETMENT',
        0.941,
        '2026-05-15 08:30:00+00',
        '2026-08-22 09:45:00+00',
        'Sentinel-2B-MSI-L2A',
        '{"item_id": "S2B_MSIL2A_20260822_T34UFB", "cloud_cover": 0.8}'::jsonb
    ),
    (
        'e5f6a7b8-c9d0-41e2-f345-6789abcdef01',
        ST_GeomFromText('POLYGON((23.1900 54.1180, 23.2080 54.1180, 23.2080 54.1290, 23.1900 54.1290, 23.1900 54.1180))', 4326),
        'INDUSTRIAL_BUILDING',
        0.893,
        '2026-05-15 08:30:00+00',
        '2026-09-18 10:20:00+00',
        'Sentinel-2A-MSI-L2A',
        '{"item_id": "S2A_MSIL2A_20260918_T34UFB", "cloud_cover": 3.4}'::jsonb
    )
ON CONFLICT (id) DO NOTHING;
