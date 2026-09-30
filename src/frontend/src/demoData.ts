/**
 * Demo Mode Interception and Static GEOINT Data Handler.
 *
 * Enables 100% static client-side operation for GitHub Pages hosting without
 * requiring the FastAPI / PostGIS / ML backend.
 *
 * Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
 */

export const isDemoMode = (): boolean => {
  if (typeof window === "undefined") return false;
  return (
    import.meta.env.VITE_APP_DEMO_MODE === "true" ||
    window.location.hostname.includes("github.io") ||
    localStorage.getItem("caelum_demo_mode") === "true"
  );
};

export const getBaseUrl = (): string => {
  return import.meta.env.BASE_URL || "/";
};

// Storage keys for optimistic client-side edits during demo
const STORAGE_REVIEWS_KEY = "caelum_demo_reviews";
const STORAGE_AUDIT_KEY = "caelum_demo_audits";
const STORAGE_COMMENTS_KEY = "caelum_demo_comments";

interface ReviewEdit {
  review_status: string;
  analyst_notes?: string;
}

export function getLocalReviews(): Record<string, ReviewEdit> {
  try {
    const raw = sessionStorage.getItem(STORAGE_REVIEWS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function saveLocalReview(id: string, review: ReviewEdit): void {
  try {
    const existing = getLocalReviews();
    existing[id] = review;
    sessionStorage.setItem(STORAGE_REVIEWS_KEY, JSON.stringify(existing));
  } catch (err) {
    console.warn("Failed to persist demo review edit", err);
  }
}

export function getLocalAudits(detectionId: string): any[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_AUDIT_KEY);
    const map = raw ? JSON.parse(raw) : {};
    return map[detectionId] || [];
  } catch {
    return [];
  }
}

export function appendLocalAudit(detectionId: string, event: any): void {
  try {
    const raw = sessionStorage.getItem(STORAGE_AUDIT_KEY);
    const map = raw ? JSON.parse(raw) : {};
    if (!map[detectionId]) map[detectionId] = [];
    map[detectionId].unshift(event);
    sessionStorage.setItem(STORAGE_AUDIT_KEY, JSON.stringify(map));
  } catch (err) {
    console.warn("Failed to persist demo audit log", err);
  }
}

export function getLocalComments(detectionId: string): any[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_COMMENTS_KEY);
    const map = raw ? JSON.parse(raw) : {};
    return map[detectionId] || [];
  } catch {
    return [];
  }
}

export function appendLocalComment(detectionId: string, comment: any): void {
  try {
    const raw = sessionStorage.getItem(STORAGE_COMMENTS_KEY);
    const map = raw ? JSON.parse(raw) : {};
    if (!map[detectionId]) map[detectionId] = [];
    map[detectionId].push(comment);
    sessionStorage.setItem(STORAGE_COMMENTS_KEY, JSON.stringify(map));
  } catch (err) {
    console.warn("Failed to persist demo comment", err);
  }
}

/**
 * Generate simulated 3D radar viewshed polygon around given coordinate.
 */
function generateRadarViewshedPolygon(centerLon: number, centerLat: number) {
  const points: [number, number][] = [];
  const radius = 0.085; // ~9km radius in degrees
  const numSteps = 48;

  for (let i = 0; i <= numSteps; i++) {
    const angle = (i / numSteps) * 2 * Math.PI;
    // Simulate terrain blockage notches
    let r = radius;
    if (angle > 1.2 && angle < 1.8) {
      r *= 0.45; // Hill blockage to the east
    } else if (angle > 3.8 && angle < 4.4) {
      r *= 0.6; // Ridge blockage to southwest
    }
    const lon = centerLon + r * Math.cos(angle) * 1.5;
    const lat = centerLat + r * Math.sin(angle);
    points.push([lon, lat]);
  }

  return {
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [points],
    },
    properties: {
      name: "AN/MPQ-64 Sentinel Radar 3D Viewshed LOS",
      radius_km: 12.0,
      radar_height_m: 25.0,
      elevation_m: 242.0,
      target_altitude_m: 100.0,
    },
  };
}

/**
 * Handle incoming API requests in Demo Mode by serving static JSON payloads
 * and handling optimistic state mutations.
 */
export async function handleDemoApiRequest(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const base = getBaseUrl();
  const method = (options.method || "GET").toUpperCase();
  const parsedUrl = new URL(url, window.location.origin);
  const path = parsedUrl.pathname;

  const jsonResponse = (data: any, status = 200) => {
    return new Response(JSON.stringify(data), {
      status,
      headers: {
        "Content-Type": "application/json",
        "X-Caelum-Demo-Mode": "true",
      },
    });
  };

  // 1. Auth token
  if (path.includes("/api/v1/auth/token")) {
    return jsonResponse({
      access_token: "demo-jwt-token-guest",
      token_type: "bearer",
      username: "analyst_viper",
      role: "analyst",
    });
  }

  // 2. Detections
  if (path.endsWith("/api/v1/detections") && method === "GET") {
    try {
      const res = await fetch(`${base}demo-data/detections.geojson`);
      if (!res.ok) throw new Error("Failed to fetch demo detections");
      const geojson = await res.json();

      // Apply any local optimistic reviews
      const localReviews = getLocalReviews();
      if (geojson.features) {
        geojson.features = geojson.features.map((f: any) => {
          const edit = localReviews[f.id];
          if (edit) {
            return {
              ...f,
              properties: {
                ...f.properties,
                review_status: edit.review_status,
                analyst_notes: edit.analyst_notes ?? f.properties.analyst_notes,
              },
            };
          }
          return f;
        });
      }
      return jsonResponse(geojson);
    } catch (err) {
      console.error("Demo mode: fallback detections error", err);
      return jsonResponse({ type: "FeatureCollection", features: [] });
    }
  }

  // 3. Review Patch: /api/v1/detections/{id}/review
  const reviewMatch = path.match(/\/api\/v1\/detections\/([^/]+)\/review/);
  if (reviewMatch && method === "PATCH") {
    const detId = reviewMatch[1];
    let body: any = {};
    if (typeof options.body === "string") {
      try {
        body = JSON.parse(options.body);
      } catch {
        // ignore
      }
    }
    saveLocalReview(detId, {
      review_status: body.review_status || "VERIFIED",
      analyst_notes: body.analyst_notes,
    });
    appendLocalAudit(detId, {
      timestamp: new Date().toISOString(),
      analyst: "analyst_viper",
      action: "STATUS_CHANGED",
      new_status: body.review_status || "VERIFIED",
      notes: body.analyst_notes || "Review status updated via Demo UI.",
    });
    return jsonResponse({
      id: detId,
      message: "Detection review updated (Demo Mode).",
      status: body.review_status,
    });
  }

  // 4. Audit Log: /api/v1/detections/{id}/audit
  const auditMatch = path.match(/\/api\/v1\/detections\/([^/]+)\/audit/);
  if (auditMatch && method === "GET") {
    const detId = auditMatch[1];
    try {
      const res = await fetch(`${base}demo-data/analytics.json`);
      const analytics = await res.json();
      const baseAudits = (analytics.audit && analytics.audit[detId]) || [
        {
          timestamp: "2026-09-14T08:00:00Z",
          analyst: "system_prithvi_v2",
          action: "AUTO_DETECTED",
          notes: "Confidence score: 0.94. Identified in Sentinel-2 multi-spectral difference pass.",
        },
      ];
      const localAudits = getLocalAudits(detId);
      return jsonResponse([...localAudits, ...baseAudits]);
    } catch {
      return jsonResponse([]);
    }
  }

  // 5. Comments: /api/v1/detections/{id}/comments
  const commentsMatch = path.match(/\/api\/v1\/detections\/([^/]+)\/comments/);
  if (commentsMatch) {
    const detId = commentsMatch[1];
    if (method === "GET") {
      try {
        const res = await fetch(`${base}demo-data/analytics.json`);
        const analytics = await res.json();
        const baseComments = (analytics.comments && analytics.comments[detId]) || [];
        const localComments = getLocalComments(detId);
        return jsonResponse([...baseComments, ...localComments]);
      } catch {
        return jsonResponse([]);
      }
    } else if (method === "POST") {
      let body: any = {};
      if (typeof options.body === "string") {
        try {
          body = JSON.parse(options.body);
        } catch {
          // ignore
        }
      }
      const newComment = {
        id: `c-${Date.now()}`,
        author: "analyst_viper",
        role: "analyst",
        timestamp: new Date().toISOString(),
        text: body.text || body.content || "Demonstration comment.",
      };
      appendLocalComment(detId, newComment);
      return jsonResponse(newComment);
    }
  }

  // 6. Zones Summary
  if (path.includes("/api/v1/zones/summary")) {
    try {
      const res = await fetch(`${base}demo-data/zones.json`);
      if (res.ok) return jsonResponse(await res.json());
      const aRes = await fetch(`${base}demo-data/analytics.json`);
      const analytics = await aRes.json();
      return jsonResponse(analytics.zones || []);
    } catch {
      return jsonResponse([]);
    }
  }

  // 7. Dark Events (Telemetry)
  if (path.includes("/api/v1/telemetry/dark-events")) {
    try {
      const res = await fetch(`${base}demo-data/dark_events.json`);
      if (res.ok) return jsonResponse(await res.json());
      const aRes = await fetch(`${base}demo-data/analytics.json`);
      const analytics = await aRes.json();
      return jsonResponse(analytics.dark_events || []);
    } catch {
      return jsonResponse([]);
    }
  }

  // 8. Network Snapshots & Graph
  if (path.includes("/api/v1/network/snapshots/latest")) {
    try {
      const res = await fetch(`${base}demo-data/network.json`);
      if (res.ok) return jsonResponse(await res.json());
      const aRes = await fetch(`${base}demo-data/analytics.json`);
      const analytics = await aRes.json();
      return jsonResponse(analytics.network || {});
    } catch {
      return jsonResponse({});
    }
  }

  if (path.endsWith("/api/v1/network/snapshots")) {
    try {
      const res = await fetch(`${base}demo-data/network.json`);
      const snap = await res.json();
      return jsonResponse([snap]);
    } catch {
      return jsonResponse([]);
    }
  }

  if (path.includes("/api/v1/network/graph")) {
    try {
      const res = await fetch(`${base}demo-data/network.json`);
      const snap = await res.json();
      return jsonResponse({
        nodes: snap.nodes || [],
        links: snap.links || snap.edges || [],
      });
    } catch {
      return jsonResponse({ nodes: [], links: [] });
    }
  }

  if (path.includes("/api/v1/network/analyse")) {
    return jsonResponse({
      node_count: 8,
      edge_count: 8,
      critical_node_ids: ["det-depot-003", "det-runway-002", "det-radar-001"],
      predicted_expansion_ids: ["det-bunker-005", "det-sam-004"],
      centrality_scores: {
        "det-radar-001": 0.68,
        "det-depot-003": 0.82,
        "det-runway-002": 0.75,
      },
      threat_flow_scores: {
        "det-radar-001": 4.12,
        "det-depot-003": 5.86,
      },
      computed_at: new Date().toISOString(),
    });
  }

  // 9. Velocity Analytics
  if (path.includes("/api/v1/analytics/velocity")) {
    try {
      const aRes = await fetch(`${base}demo-data/analytics.json`);
      const analytics = await aRes.json();
      return jsonResponse(analytics.velocity || { time_series: [] });
    } catch {
      return jsonResponse({ time_series: [] });
    }
  }

  // 10. Viewshed computation
  if (path.includes("/api/v1/analytics/viewshed")) {
    return jsonResponse(generateRadarViewshedPolygon(23.185, 54.165));
  }

  // 11. Cursor-on-Target (CoT) Broadcast to ATAK
  const cotMatch = path.match(/\/api\/v1\/cot\/broadcast\/([^/]+)/);
  if (cotMatch && method === "POST") {
    const targetId = cotMatch[1];
    return jsonResponse({
      status: "dispatched",
      target_id: targetId,
      cot_type: "a-h-G-U-C",
      tak_server: "demo-tak-server.caelum.local:8089",
      dispatched_at: new Date().toISOString(),
    });
  }

  // 12. Active Learning LoRA Trigger
  if (path.includes("/api/v1/mlops/active-learning/trigger")) {
    return jsonResponse({
      status: "queued",
      iteration_tag: "v2.1-demo",
      candidates_queued: 4,
      fp_suppression_rate: 0.892,
    });
  }

  // 13. SITREPs
  if (path.endsWith("/api/v1/sitreps") && method === "GET") {
    try {
      const res = await fetch(`${base}demo-data/sitreps.json`);
      if (res.ok) return jsonResponse(await res.json());
      const aRes = await fetch(`${base}demo-data/analytics.json`);
      const analytics = await aRes.json();
      return jsonResponse(analytics.sitreps || []);
    } catch {
      return jsonResponse([]);
    }
  }

  if (path.includes("/api/v1/sitreps/generate")) {
    return jsonResponse({
      id: `sitrep-gen-${Date.now()}`,
      title: "SITREP-TACTICAL-DEMO: Automated LLM Intelligence Assessment",
      classification: "TOP SECRET // NOFORN // AIR-GAPPED GEOINT",
      author: "Autonomous SITREP Generator (Local DeepSeek-R1-14B)",
      created_at: new Date().toISOString(),
      executive_summary: "Dynamic intelligence synthesis in demo mode confirms active logistical build-out across Sector ALPHA and BRAVO. Supply chain critical nodes verified.",
      key_findings: [
        "AN/MPQ-64 Sentinel radar site fully active on ridge +242m ASL.",
        "Tactical airstrip expansion asphalt curing completed.",
        "Force-directed RL logistics chokepoint identified at Depot 003.",
      ],
      recommended_actions: [
        "Maintain persistent satellite revisit schedule.",
        "Broadcast updated CoT tactical vectors to tactical edge teams.",
      ],
    });
  }

  // 14. Saved Views / Filters
  if (path.includes("/api/v1/saved-filters")) {
    return jsonResponse([
      {
        id: "sf-demo-1",
        name: "Tactical Radar & Airfields",
        filter_json: { min_priority: 0.8 },
      },
    ]);
  }

  // 15. Admin Config & DLQ
  if (path.includes("/api/v1/admin/config")) {
    return jsonResponse({
      prithvi_confidence_threshold: "0.75",
      yolo_confidence_threshold: "0.65",
      ais_dark_radius_km: "50.0",
      edge_sync_interval_sec: "60",
    });
  }

  if (path.includes("/api/v1/ops/dlq")) {
    return jsonResponse([]);
  }

  if (path.includes("/api/v1/export")) {
    const res = await fetch(`${base}demo-data/detections.geojson`);
    return jsonResponse(await res.json());
  }

  // Fallback 404
  return new Response(JSON.stringify({ detail: "Not found in Demo Mode" }), {
    status: 404,
    headers: { "Content-Type": "application/json" },
  });
}
