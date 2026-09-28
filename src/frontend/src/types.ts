export type InfrastructureClass =
  | "LOGISTICS_DEPOT"
  | "RUNWAY_TAXIWAY"
  | "RADAR_DOME"
  | "DEFENSE_REVETMENT"
  | "INDUSTRIAL_BUILDING"
  | "UNKNOWN_STRUCTURE";

export type ReviewStatus =
  | "PENDING_REVIEW"
  | "VERIFIED"
  | "MISCLASSIFIED"
  | "FALSE_POSITIVE";

export interface DetectionProperties {
  id: string;
  classification: InfrastructureClass;
  confidence: number;
  area_sq_meters?: number;
  baseline_timestamp: string;
  detection_timestamp: string;
  sensor_source?: string;
  zone_id?: string;
  review_status: ReviewStatus;
  verified_class?: InfrastructureClass | null;
  priority_score: number;
  reviewer_notes?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  baseline_chip_path?: string;
  detection_chip_path?: string;
  stac_metadata?: Record<string, any>;
}

export interface DetectionFeature {
  type: "Feature";
  id: string;
  geometry: {
    type: "Polygon";
    coordinates: number[][][];
  };
  properties: DetectionProperties;
}

export interface DetectionFeatureCollection {
  type: "FeatureCollection";
  features: DetectionFeature[];
}

export interface ZoneSummary {
  id: string;
  name: string;
  alert_level: "HIGH" | "ELEVATED" | "NORMAL";
  boundary: {
    type: "Polygon";
    coordinates: number[][][];
  };
  total_detections: number;
  new_detections_24h: number;
  new_detections_7d: number;
  high_priority_count: number;
  classification_breakdown: Record<string, number>;
}

export interface ImageryMetadata {
  detection_id: string;
  t0_image_url: string;
  t1_image_url: string;
  mask_image_url: string;
  sensor_source: string;
  baseline_timestamp: string;
  detection_timestamp: string;
  stac_metadata: Record<string, any>;
}

export interface AuthUser {
  id: string;
  username: string;
  role: "viewer" | "analyst" | "admin";
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  role: "viewer" | "analyst" | "admin";
  username: string;
}

export interface DetectionComment {
  id: string;
  detection_id: string;
  user_id?: string | null;
  username: string;
  comment: string;
  created_at: string;
}

export interface DetectionAuditRecord {
  id: string;
  detection_id: string;
  previous_state?: string | null;
  new_state: string;
  user_id?: string | null;
  username: string;
  note?: string | null;
  timestamp: string;
}

export interface SavedFilter {
  id: string;
  user_id: string;
  name: string;
  filter_json: {
    classification?: string;
    review_status?: string;
    min_confidence?: number;
    zone_id?: string;
    [key: string]: any;
  };
  created_at: string;
}

export interface SystemConfig {
  id?: number;
  key: string;
  value: string;
  description?: string | null;
  updated_by?: string | null;
  updated_at?: string | null;
}

export interface GeofenceConfig {
  name: string;
  bbox: [number, number, number, number];
  description?: string;
}
