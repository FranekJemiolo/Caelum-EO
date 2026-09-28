-- Project Caelum-EO: Version 3 Migrations
-- Analyst Usability, Dynamic Configuration, and Enterprise Audit Tracking
-- Repository: github.com/FranekJemiolo/Caelum-EO

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Dynamic System Configurations Table
CREATE TABLE IF NOT EXISTS system_configurations (
    id SERIAL PRIMARY KEY,
    key VARCHAR(128) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_system_configurations_key ON system_configurations (key);

-- 2. Analyst Threaded Notes / Comments
CREATE TABLE IF NOT EXISTS detection_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id UUID NOT NULL REFERENCES infrastructure_detections(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(128) NOT NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_detection_comments_detection_id ON detection_comments (detection_id);
CREATE INDEX IF NOT EXISTS idx_detection_comments_created_at ON detection_comments (created_at ASC);

-- 3. Detection Lifecycle Audit Log
CREATE TABLE IF NOT EXISTS detection_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id UUID NOT NULL REFERENCES infrastructure_detections(id) ON DELETE CASCADE,
    previous_state VARCHAR(64),
    new_state VARCHAR(64) NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(128) NOT NULL,
    note TEXT,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_detection_audit_detection_id ON detection_audit_log (detection_id);
CREATE INDEX IF NOT EXISTS idx_detection_audit_timestamp ON detection_audit_log (timestamp DESC);

-- 4. Analyst Saved Filter Views
CREATE TABLE IF NOT EXISTS saved_filters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    filter_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_saved_filters_user_id ON saved_filters (user_id);

-- 5. Seed Initial System Configurations
INSERT INTO system_configurations (key, value, description) VALUES
    ('ml_confidence_threshold', '0.60', 'Minimum inference confidence score required to ingest detection into intelligence store'),
    ('stac_polling_interval_seconds', '300', 'STAC catalog ingestion polling frequency in seconds'),
    ('dlq_topic', 'caelum.dlq', 'Kafka Dead Letter Queue topic name for unparseable or failed messages'),
    ('webhook_url', 'http://localhost:8000/api/v1/webhooks/alerts', 'Local webhook endpoint for critical GEOINT triage alerts'),
    ('target_geofences', '[{"name": "Suwalki Corridor", "bbox": [23.00, 54.00, 23.50, 54.40]}, {"name": "Northern Frontier", "bbox": [23.00, 54.40, 23.50, 54.70]}, {"name": "Western Logistics", "bbox": [22.60, 53.90, 23.00, 54.30]}]', 'Target geographic bounding boxes (geofences) actively polled by STAC collectors')
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    description = EXCLUDED.description;
