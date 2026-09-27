-- Project Caelum-EO: PostGIS Database Initialization Script
-- Mounted into PostGIS 15+ container at /docker-entrypoint-initdb.d/init.sql
-- Repository: github.com/FranekJemiolo/Caelum-EO

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Domain Classification Enum
DO $$ BEGIN
    CREATE TYPE infrastructure_class AS ENUM (
        'LOGISTICS_DEPOT',
        'RUNWAY_TAXIWAY',
        'RADAR_DOME',
        'DEFENSE_REVETMENT',
        'INDUSTRIAL_BUILDING',
        'UNKNOWN_STRUCTURE'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Review Status Enum for Human-in-the-Loop Triage
DO $$ BEGIN
    CREATE TYPE review_status_enum AS ENUM (
        'PENDING_REVIEW',
        'VERIFIED',
        'MISCLASSIFIED',
        'FALSE_POSITIVE'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 1. Zone Definition Table for Geospatial Aggregation
CREATE TABLE IF NOT EXISTS geographic_zones (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    boundary GEOMETRY(Polygon, 4326) NOT NULL,
    alert_level VARCHAR(32) DEFAULT 'NORMAL',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_zones_boundary ON geographic_zones USING GIST (boundary);

-- 2. Primary Spatial Intelligence Table
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
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    -- Phase 3 Triage & Review Extensions
    zone_id VARCHAR(64) REFERENCES geographic_zones(id) ON DELETE SET NULL,
    review_status review_status_enum DEFAULT 'PENDING_REVIEW',
    verified_class infrastructure_class,
    priority_score REAL DEFAULT 0.0,
    reviewer_notes TEXT,
    reviewed_by VARCHAR(128),
    reviewed_at TIMESTAMPTZ,
    baseline_chip_path VARCHAR(512),
    detection_chip_path VARCHAR(512)
);

-- Ensure all Phase 3 columns exist if table was already created
ALTER TABLE infrastructure_detections
    ADD COLUMN IF NOT EXISTS zone_id VARCHAR(64) REFERENCES geographic_zones(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS review_status review_status_enum DEFAULT 'PENDING_REVIEW',
    ADD COLUMN IF NOT EXISTS verified_class infrastructure_class,
    ADD COLUMN IF NOT EXISTS priority_score REAL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS reviewer_notes TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(128),
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS baseline_chip_path VARCHAR(512),
    ADD COLUMN IF NOT EXISTS detection_chip_path VARCHAR(512);

-- Indexes for Fast Geospatial, Temporal, and Triage Filtering
CREATE INDEX IF NOT EXISTS idx_infra_detections_geom
    ON infrastructure_detections USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_infra_detections_timestamp
    ON infrastructure_detections (detection_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_infra_detections_class
    ON infrastructure_detections (classification);

CREATE INDEX IF NOT EXISTS idx_detections_review_status
    ON infrastructure_detections (review_status);

CREATE INDEX IF NOT EXISTS idx_detections_priority
    ON infrastructure_detections (priority_score DESC);

CREATE INDEX IF NOT EXISTS idx_detections_zone
    ON infrastructure_detections (zone_id);

-- 3. Review Audit Log Table for HITL Tracking
CREATE TABLE IF NOT EXISTS review_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id UUID NOT NULL REFERENCES infrastructure_detections(id) ON DELETE CASCADE,
    previous_status review_status_enum,
    new_status review_status_enum NOT NULL,
    previous_class infrastructure_class,
    verified_class infrastructure_class,
    reviewer_notes TEXT,
    reviewed_by VARCHAR(128) NOT NULL,
    reviewed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_detection_id ON review_audit_log (detection_id);
CREATE INDEX IF NOT EXISTS idx_audit_reviewed_at ON review_audit_log (reviewed_at DESC);

-- 4. Seed Strategic Geographic Surveillance Zones
INSERT INTO geographic_zones (id, name, boundary, alert_level) VALUES
    (
        'ZONE-SUWALKI-CORRIDOR',
        'Suwalki Gap Strategic Corridor',
        ST_GeomFromText('POLYGON((23.00 54.00, 23.50 54.00, 23.50 54.40, 23.00 54.40, 23.00 54.00))', 4326),
        'HIGH'
    ),
    (
        'ZONE-NORTH-SECTOR',
        'Northern Frontier Observation Sector',
        ST_GeomFromText('POLYGON((23.00 54.40, 23.50 54.40, 23.50 54.70, 23.00 54.70, 23.00 54.40))', 4326),
        'ELEVATED'
    ),
    (
        'ZONE-WEST-LOGISTICS',
        'Western Staging Logistics Sector',
        ST_GeomFromText('POLYGON((22.60 53.90, 23.00 53.90, 23.00 54.30, 22.60 54.30, 22.60 53.90))', 4326),
        'NORMAL'
    )
ON CONFLICT (id) DO NOTHING;

-- 5. Seed Initial Strategic Detections with Triage Metadata
INSERT INTO infrastructure_detections (
    id, geometry, classification, confidence, baseline_timestamp, detection_timestamp, sensor_source, stac_metadata,
    zone_id, review_status, priority_score, baseline_chip_path, detection_chip_path
) VALUES
    (
        'a1b2c3d4-e5f6-47a8-b901-23456789abcd',
        ST_GeomFromText('POLYGON((23.1480 54.1180, 23.1560 54.1180, 23.1560 54.1260, 23.1480 54.1260, 23.1480 54.1180))', 4326),
        'RADAR_DOME',
        0.965,
        '2026-05-15 08:30:00+00',
        '2026-05-15 08:30:00+00',
        'Sentinel-2A-MSI-L2A',
        '{"item_id": "S2A_MSIL2A_20260515_T34UFB", "cloud_cover": 2.1}'::jsonb,
        'ZONE-SUWALKI-CORRIDOR',
        'PENDING_REVIEW',
        0.95,
        'data/chips/a1b2c3d4/t0.png',
        'data/chips/a1b2c3d4/t1.png'
    ),
    (
        'b2c3d4e5-f6a7-48b9-c012-3456789abcde',
        ST_GeomFromText('POLYGON((23.1800 54.1000, 23.2100 54.1000, 23.2100 54.1150, 23.1800 54.1150, 23.1800 54.1000))', 4326),
        'LOGISTICS_DEPOT',
        0.912,
        '2026-05-15 08:30:00+00',
        '2026-06-02 11:15:00+00',
        'Sentinel-2B-MSI-L2A',
        '{"item_id": "S2B_MSIL2A_20260602_T34UFB", "cloud_cover": 4.5}'::jsonb,
        'ZONE-SUWALKI-CORRIDOR',
        'PENDING_REVIEW',
        0.82,
        'data/chips/b2c3d4e5/t0.png',
        'data/chips/b2c3d4e5/t1.png'
    ),
    (
        'c3d4e5f6-a7b8-49c0-d123-456789abcdef',
        ST_GeomFromText('POLYGON((23.2800 54.1950, 23.3550 54.2000, 23.3500 54.2150, 23.2750 54.2100, 23.2800 54.1950))', 4326),
        'RUNWAY_TAXIWAY',
        0.984,
        '2026-05-15 08:30:00+00',
        '2026-07-10 14:00:00+00',
        'Sentinel-2A-MSI-L2A',
        '{"item_id": "S2A_MSIL2A_20260710_T34UFB", "cloud_cover": 1.2}'::jsonb,
        'ZONE-SUWALKI-CORRIDOR',
        'PENDING_REVIEW',
        0.98,
        'data/chips/c3d4e5f6/t0.png',
        'data/chips/c3d4e5f6/t1.png'
    ),
    (
        'd4e5f6a7-b8c9-40d1-e234-56789abcdef0',
        ST_GeomFromText('POLYGON((23.2200 54.1300, 23.2380 54.1300, 23.2380 54.1440, 23.2200 54.1440, 23.2200 54.1300))', 4326),
        'DEFENSE_REVETMENT',
        0.941,
        '2026-05-15 08:30:00+00',
        '2026-08-22 09:45:00+00',
        'Sentinel-2B-MSI-L2A',
        '{"item_id": "S2B_MSIL2A_20260822_T34UFB", "cloud_cover": 0.8}'::jsonb,
        'ZONE-SUWALKI-CORRIDOR',
        'VERIFIED',
        0.75,
        'data/chips/d4e5f6a7/t0.png',
        'data/chips/d4e5f6a7/t1.png'
    ),
    (
        'e5f6a7b8-c9d0-41e2-f345-6789abcdef01',
        ST_GeomFromText('POLYGON((23.1900 54.1180, 23.2080 54.1180, 23.2080 54.1290, 23.1900 54.1290, 23.1900 54.1180))', 4326),
        'INDUSTRIAL_BUILDING',
        0.893,
        '2026-05-15 08:30:00+00',
        '2026-09-18 10:20:00+00',
        'Sentinel-2A-MSI-L2A',
        '{"item_id": "S2A_MSIL2A_20260918_T34UFB", "cloud_cover": 3.4}'::jsonb,
        'ZONE-SUWALKI-CORRIDOR',
        'PENDING_REVIEW',
        0.65,
        'data/chips/e5f6a7b8/t0.png',
        'data/chips/e5f6a7b8/t1.png'
    )
ON CONFLICT (id) DO UPDATE SET
    zone_id = EXCLUDED.zone_id,
    review_status = EXCLUDED.review_status,
    priority_score = EXCLUDED.priority_score,
    baseline_chip_path = EXCLUDED.baseline_chip_path,
    detection_chip_path = EXCLUDED.detection_chip_path;
