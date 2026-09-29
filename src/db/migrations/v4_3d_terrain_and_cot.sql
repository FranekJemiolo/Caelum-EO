-- Project Caelum-EO: Version 4 Migrations
-- 3D Terrain Analytics, Viewshed Line-of-Sight, Cursor-on-Target (CoT), and Generative SITREPs
-- Repository: github.com/FranekJemiolo/Caelum-EO

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Extend infrastructure_detections with 3D elevation and CoT tracking
ALTER TABLE infrastructure_detections 
    ADD COLUMN IF NOT EXISTS elevation_msl DOUBLE PRECISION DEFAULT 165.0,
    ADD COLUMN IF NOT EXISTS elevation_origin VARCHAR(64) DEFAULT 'Copernicus-GLO-30',
    ADD COLUMN IF NOT EXISTS cot_broadcast_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cot_status VARCHAR(32) DEFAULT 'QUEUED';

-- 2. Radar Viewshed Line-of-Sight Calculations Cache Table
CREATE TABLE IF NOT EXISTS viewshed_calculations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id UUID REFERENCES infrastructure_detections(id) ON DELETE CASCADE,
    observer_lon DOUBLE PRECISION NOT NULL,
    observer_lat DOUBLE PRECISION NOT NULL,
    observer_elevation_msl DOUBLE PRECISION NOT NULL,
    antenna_height_m DOUBLE PRECISION NOT NULL DEFAULT 15.0,
    radius_km DOUBLE PRECISION NOT NULL DEFAULT 12.0,
    geometry GEOMETRY(Geometry, 4326) NOT NULL,
    visible_area_sq_km DOUBLE PRECISION NOT NULL,
    coverage_percentage DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_viewshed_calc_detection_id ON viewshed_calculations (detection_id);
CREATE INDEX IF NOT EXISTS idx_viewshed_calc_geometry ON viewshed_calculations USING GIST (geometry);

-- 3. Generative AI Daily SITREP Intelligence Reports Table
CREATE TABLE IF NOT EXISTS sitrep_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    time_window_start TIMESTAMPTZ NOT NULL,
    time_window_end TIMESTAMPTZ NOT NULL,
    model_name VARCHAR(128) NOT NULL DEFAULT 'llama3:8b-instruct',
    raw_prompt TEXT,
    sitrep_content TEXT NOT NULL,
    target_count INTEGER NOT NULL DEFAULT 0,
    high_priority_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'GENERATED',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sitrep_reports_created_at ON sitrep_reports (created_at DESC);
