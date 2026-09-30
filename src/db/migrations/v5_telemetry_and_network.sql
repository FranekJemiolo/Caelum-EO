-- Project Caelum-EO: Version 5 Migrations
-- Predictive Intelligence: Multi-Modal Telemetry Ingestion, Logistics Network & RL Analytics
-- Repository: github.com/FranekJemiolo/Caelum-EO

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================================
-- 1. AIS Vessel Track Table
-- Stores Maritime Automatic Identification System (AIS) transponder tracks.
-- Ingested from local CSV/JSON dumps sourced from external HDD or SIGINT feed.
-- ============================================================================
CREATE TABLE IF NOT EXISTS vessel_tracks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(9) NOT NULL,                          -- Maritime Mobile Service Identity
    vessel_name VARCHAR(255),
    vessel_type VARCHAR(64),                            -- e.g. "CARGO", "TANKER", "MILITARY"
    flag VARCHAR(8),                                    -- ISO 3166-1 alpha-2 country code
    timestamp TIMESTAMPTZ NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    speed_knots DOUBLE PRECISION,
    course_deg DOUBLE PRECISION,
    heading_deg DOUBLE PRECISION,
    draught_m DOUBLE PRECISION,
    navigational_status VARCHAR(64),                   -- e.g. "UNDERWAY_ENGINE", "AT_ANCHOR"
    is_dark BOOLEAN NOT NULL DEFAULT FALSE,             -- TRUE = transponder went offline
    dark_duration_minutes INTEGER,                      -- Minutes the transponder was dark
    dark_near_infra_km DOUBLE PRECISION,               -- Distance to nearest EO detection (km) when dark
    dark_near_detection_id UUID REFERENCES infrastructure_detections(id) ON DELETE SET NULL,
    geometry GEOMETRY(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED,
    source_file VARCHAR(512),                           -- Provenance: originating dump file path
    ingested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vessel_tracks_mmsi ON vessel_tracks (mmsi);
CREATE INDEX IF NOT EXISTS idx_vessel_tracks_timestamp ON vessel_tracks (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_vessel_tracks_geometry ON vessel_tracks USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_vessel_tracks_is_dark ON vessel_tracks (is_dark) WHERE is_dark = TRUE;

-- ============================================================================
-- 2. ADS-B Aircraft Track Table
-- Stores Automatic Dependent Surveillance-Broadcast (ADS-B) transponder tracks.
-- Ingested from local JSON/CSV files from a ground-based ADS-B receiver.
-- ============================================================================
CREATE TABLE IF NOT EXISTS aircraft_tracks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    icao24 VARCHAR(6) NOT NULL,                        -- ICAO 24-bit Mode S address (hex)
    callsign VARCHAR(8),
    country_of_origin VARCHAR(64),
    aircraft_category VARCHAR(32),                     -- e.g. "CARGO", "MILITARY", "HELICOPTER"
    timestamp TIMESTAMPTZ NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    altitude_baro_m DOUBLE PRECISION,                  -- Barometric altitude in metres
    altitude_geo_m DOUBLE PRECISION,                   -- Geometric altitude in metres
    speed_ms DOUBLE PRECISION,                         -- Ground speed in m/s
    vertical_rate_ms DOUBLE PRECISION,                 -- Vertical rate in m/s
    heading_deg DOUBLE PRECISION,
    squawk VARCHAR(4),                                 -- ATC transponder squawk code
    is_on_ground BOOLEAN NOT NULL DEFAULT FALSE,
    is_dark BOOLEAN NOT NULL DEFAULT FALSE,
    dark_near_infra_km DOUBLE PRECISION,
    dark_near_detection_id UUID REFERENCES infrastructure_detections(id) ON DELETE SET NULL,
    geometry GEOMETRY(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED,
    source_file VARCHAR(512),
    ingested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_aircraft_tracks_icao24 ON aircraft_tracks (icao24);
CREATE INDEX IF NOT EXISTS idx_aircraft_tracks_timestamp ON aircraft_tracks (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_aircraft_tracks_geometry ON aircraft_tracks USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_aircraft_tracks_is_dark ON aircraft_tracks (is_dark) WHERE is_dark = TRUE;

-- ============================================================================
-- 3. Dark Event Correlation Table
-- Aggregated "Dark Target" events: transponder-off events that correlate
-- spatiotemporally with known infrastructure detections.
-- ============================================================================
CREATE TABLE IF NOT EXISTS dark_target_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(16) NOT NULL CHECK (event_type IN ('AIS', 'ADSB')),
    entity_id VARCHAR(16) NOT NULL,                    -- MMSI (AIS) or ICAO24 (ADS-B)
    entity_name VARCHAR(255),
    detection_id UUID NOT NULL REFERENCES infrastructure_detections(id) ON DELETE CASCADE,
    dark_start TIMESTAMPTZ NOT NULL,
    dark_end TIMESTAMPTZ,
    duration_minutes INTEGER,
    closest_approach_km DOUBLE PRECISION NOT NULL,
    threat_score DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (threat_score BETWEEN 0.0 AND 1.0),
    analyst_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    analyst_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dark_events_detection_id ON dark_target_events (detection_id);
CREATE INDEX IF NOT EXISTS idx_dark_events_event_type ON dark_target_events (event_type);
CREATE INDEX IF NOT EXISTS idx_dark_events_threat_score ON dark_target_events (threat_score DESC);
CREATE INDEX IF NOT EXISTS idx_dark_events_dark_start ON dark_target_events (dark_start DESC);

-- ============================================================================
-- 4. Logistics Network Graph Snapshot Table
-- Persists computed graph snapshots (nodes=detections, edges=telemetry paths)
-- from the NetworkX RL engine for historical comparison and trend analysis.
-- ============================================================================
CREATE TABLE IF NOT EXISTS network_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_label VARCHAR(255) NOT NULL,
    computation_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    node_count INTEGER NOT NULL DEFAULT 0,
    edge_count INTEGER NOT NULL DEFAULT 0,
    critical_node_ids TEXT[] NOT NULL DEFAULT '{}',     -- UUIDs of predicted critical infrastructure nodes
    predicted_expansion_ids TEXT[] NOT NULL DEFAULT '{}', -- UUIDs of predicted next build-out locations
    rl_episode_rewards DOUBLE PRECISION[],             -- RL agent rewards per episode during training
    rl_model_path VARCHAR(512),                        -- Local path to saved SB3 model checkpoint
    graph_json JSONB NOT NULL,                         -- Full node-link graph serialisation (networkx.readwrite.json_graph)
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_network_snapshots_created_at ON network_snapshots (created_at DESC);

-- ============================================================================
-- 5. Seed V5 System Configuration keys
-- ============================================================================
INSERT INTO system_configurations (key, value, description) VALUES
    ('ais_dark_radius_km', '50', 'Radius in km around an EO detection within which a dark AIS event is flagged as suspicious'),
    ('ais_dark_time_window_hours', '72', 'Time window in hours before/after a detection change-event for dark AIS correlation'),
    ('adsb_dark_radius_km', '30', 'Radius in km around an EO detection within which a dark ADS-B event is flagged as suspicious'),
    ('rl_training_episodes', '500', 'Number of RL training episodes for logistics network graph agent'),
    ('network_snapshot_retention_days', '90', 'Days to retain logistics network graph snapshots before pruning')
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    description = EXCLUDED.description;
