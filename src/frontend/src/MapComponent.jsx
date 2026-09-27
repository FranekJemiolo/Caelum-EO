import React, { useState, useEffect, useMemo, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import Map from 'react-map-gl/maplibre';
import { Play, Pause, Radio, Activity, Shield, Calendar, Layers, X, Info } from 'lucide-react';

// Suwalki Gap Strategic Surveillance Corridor Viewport
const INITIAL_VIEW_STATE = {
  longitude: 23.23,
  latitude: 54.14,
  zoom: 11.4,
  pitch: 45,
  bearing: -15
};

const DARK_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

// Classification color mapping adhering strictly to the PostGIS enum
export const CLASSIFICATION_COLORS = {
  RUNWAY_TAXIWAY: { rgb: [249, 115, 22], hex: '#f97316', label: 'Runway / Taxiway' },      // Orange
  RADAR_DOME: { rgb: [239, 68, 68], hex: '#ef4444', label: 'Radar Dome' },                 // Red
  LOGISTICS_DEPOT: { rgb: [234, 179, 8], hex: '#eab308', label: 'Logistics Depot' },       // Yellow
  DEFENSE_REVETMENT: { rgb: [244, 63, 94], hex: '#f43f5e', label: 'Defense Revetment' },   // Crimson
  INDUSTRIAL_BUILDING: { rgb: [168, 85, 247], hex: '#a855f7', label: 'Industrial Building' }, // Purple
  UNKNOWN_STRUCTURE: { rgb: [148, 163, 184], hex: '#94a3b8', label: 'Unknown Structure' }  // Slate
};

// Initial Seed Data (matching src/db/init.sql)
const SEED_GEOINT_DATA = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.148, 54.118], [23.156, 54.118], [23.156, 54.126], [23.148, 54.126], [23.148, 54.118]]]
      },
      properties: {
        id: "a1b2c3d4-e5f6-47a8-b901-23456789abcd",
        classification: "RADAR_DOME",
        confidence: 0.965,
        area_sq_meters: 3450.0,
        baseline_timestamp: "2026-05-15T08:30:00Z",
        detection_timestamp: "2026-05-15T08:30:00Z",
        sensor_source: "Sentinel-2A-MSI-L2A"
      }
    },
    {
      type: "Feature",
      id: "b2c3d4e5-f6a7-48b9-c012-3456789abcde",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.180, 54.100], [23.210, 54.100], [23.210, 54.115], [23.180, 54.115], [23.180, 54.100]]]
      },
      properties: {
        id: "b2c3d4e5-f6a7-48b9-c012-3456789abcde",
        classification: "LOGISTICS_DEPOT",
        confidence: 0.912,
        area_sq_meters: 15400.0,
        baseline_timestamp: "2026-05-15T08:30:00Z",
        detection_timestamp: "2026-06-02T11:15:00Z",
        sensor_source: "Sentinel-2B-MSI-L2A"
      }
    },
    {
      type: "Feature",
      id: "c3d4e5f6-a7b8-49c0-d123-456789abcdef",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.280, 54.195], [23.355, 54.200], [23.350, 54.215], [23.275, 54.210], [23.280, 54.195]]]
      },
      properties: {
        id: "c3d4e5f6-a7b8-49c0-d123-456789abcdef",
        classification: "RUNWAY_TAXIWAY",
        confidence: 0.984,
        area_sq_meters: 42000.0,
        baseline_timestamp: "2026-05-15T08:30:00Z",
        detection_timestamp: "2026-07-10T14:00:00Z",
        sensor_source: "Sentinel-2A-MSI-L2A"
      }
    },
    {
      type: "Feature",
      id: "d4e5f6a7-b8c9-40d1-e234-56789abcdef0",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.220, 54.130], [23.238, 54.130], [23.238, 54.144], [23.220, 54.144], [23.220, 54.130]]]
      },
      properties: {
        id: "d4e5f6a7-b8c9-40d1-e234-56789abcdef0",
        classification: "DEFENSE_REVETMENT",
        confidence: 0.941,
        area_sq_meters: 8900.0,
        baseline_timestamp: "2026-05-15T08:30:00Z",
        detection_timestamp: "2026-08-22T09:45:00Z",
        sensor_source: "Sentinel-2B-MSI-L2A"
      }
    },
    {
      type: "Feature",
      id: "e5f6a7b8-c9d0-41e2-f345-6789abcdef01",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.190, 54.118], [23.208, 54.118], [23.208, 54.129], [23.190, 54.129], [23.190, 54.118]]]
      },
      properties: {
        id: "e5f6a7b8-c9d0-41e2-f345-6789abcdef01",
        classification: "INDUSTRIAL_BUILDING",
        confidence: 0.893,
        area_sq_meters: 6700.0,
        baseline_timestamp: "2026-05-15T08:30:00Z",
        detection_timestamp: "2026-09-18T10:20:00Z",
        sensor_source: "Sentinel-2A-MSI-L2A"
      }
    }
  ]
};

const TIMELINE_MIN = new Date('2026-05-01T00:00:00Z').getTime();
const TIMELINE_MAX = new Date('2026-09-30T23:59:59Z').getTime();

export default function MapComponent({ apiUrl = "http://localhost:8000/api/detections" }) {
  const [data, setData] = useState(SEED_GEOINT_DATA);
  const [activeClasses, setActiveClasses] = useState(new Set(Object.keys(CLASSIFICATION_COLORS)));
  const [scrubberTime, setScrubberTime] = useState(TIMELINE_MAX);
  const [isPlaying, setIsPlaying] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState(null);

  // Fetch live detections from backend if available
  useEffect(() => {
    fetch(apiUrl)
      .then(res => res.json())
      .then(json => {
        if (json && json.features && json.features.length > 0) {
          setData(json);
        }
      })
      .catch(() => {
        // Retain local seed data
      });
  }, [apiUrl]);

  // Automated temporal scrubber animation
  useEffect(() => {
    let interval;
    if (isPlaying) {
      interval = setInterval(() => {
        setScrubberTime(prev => {
          const step = 86400000 * 3; // 3 days
          if (prev + step > TIMELINE_MAX) {
            return TIMELINE_MIN;
          }
          return prev + step;
        });
      }, 700);
    }
    return () => clearInterval(interval);
  }, [isPlaying]);

  const toggleCategory = useCallback((cls) => {
    setActiveClasses(prev => {
      const next = new Set(prev);
      if (next.has(cls)) next.delete(cls);
      else next.add(cls);
      return next;
    });
  }, []);

  // Filter features by time scrubber and active categories
  const filteredFeatures = useMemo(() => {
    return (data?.features || []).filter(f => {
      const p = f.properties || {};
      const t = new Date(p.detection_timestamp || p.detection_date).getTime();
      return t <= scrubberTime && activeClasses.has(p.classification);
    });
  }, [data, scrubberTime, activeClasses]);

  const layers = useMemo(() => {
    return [
      new GeoJsonLayer({
        id: 'infrastructure-detections-layer',
        data: { type: 'FeatureCollection', features: filteredFeatures },
        pickable: true,
        stroked: true,
        filled: true,
        extruded: true,
        wireframe: true,
        lineWidthMinPixels: 2,
        getFillColor: f => {
          const cls = f.properties?.classification;
          const conf = CLASSIFICATION_COLORS[cls]?.rgb || [148, 163, 184];
          return [...conf, 190];
        },
        getLineColor: [255, 255, 255, 240],
        getElevation: f => (f.properties?.confidence || 0.5) * 80,
        autoHighlight: true,
        highlightColor: [0, 242, 254, 220],
        onClick: info => {
          if (info.object) setSelectedTarget(info.object);
        }
      })
    ];
  }, [filteredFeatures]);

  const dateLabel = useMemo(() => {
    return new Date(scrubberTime).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  }, [scrubberTime]);

  return (
    <div className="map-container">
      {/* Deck.gl Viewport */}
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller={true}
        layers={layers}
        getTooltip={({ object }) => {
          if (!object) return null;
          const p = object.properties || {};
          return {
            html: `
              <div style="font-family: sans-serif; font-size: 12px; background: rgba(10,13,20,0.95); padding: 8px 12px; border: 1px solid #00f2fe; border-radius: 6px; color: #fff;">
                <b style="color: #00f2fe;">${p.classification?.replace(/_/g, ' ')}</b><br/>
                Confidence: ${(p.confidence * 100).toFixed(1)}%<br/>
                Date: ${new Date(p.detection_timestamp || p.detection_date).toLocaleDateString()}<br/>
                Sensor: ${p.sensor_source || 'Sentinel-2'}
              </div>
            `
          };
        }}
      >
        <Map mapStyle={DARK_MAP_STYLE} />
      </DeckGL>

      {/* Floating Tactical HUD Panel */}
      <aside className="hud-panel glass-panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ background: 'linear-gradient(135deg, #00f2fe, #4facfe)', padding: 6, borderRadius: 6 }}>
            <Radio size={18} color="#000" />
          </div>
          <div>
            <h1 className="hud-title">CAELUM-EO</h1>
            <div style={{ fontSize: '0.7rem', color: '#00f2fe', fontFamily: 'monospace' }}>
              AUTONOMOUS GEOINT PIPELINE
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', fontFamily: 'monospace' }}>
            Infrastructure Classes
          </div>
          {Object.entries(CLASSIFICATION_COLORS).map(([key, item]) => {
            const count = (data?.features || []).filter(f => f.properties?.classification === key).length;
            const active = activeClasses.has(key);
            return (
              <div
                key={key}
                onClick={() => toggleCategory(key)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '5px 8px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: active ? 'rgba(0, 242, 254, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                  border: `1px solid ${active ? 'rgba(0, 242, 254, 0.3)' : 'rgba(255, 255, 255, 0.05)'}`,
                  fontSize: '0.8rem',
                  transition: 'all 0.2s'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: 2,
                      backgroundColor: item.hex,
                      opacity: active ? 1 : 0.25
                    }}
                  />
                  <span style={{ color: active ? '#fff' : '#64748b' }}>{item.label}</span>
                </div>
                <span style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: '#64748b' }}>{count}</span>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Target Details Dossier Side Drawer */}
      {selectedTarget && (
        <aside
          style={{
            position: 'absolute',
            top: 16,
            right: 16,
            width: 320,
            zIndex: 10,
            background: 'rgba(16, 22, 34, 0.9)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(64, 90, 130, 0.3)',
            borderRadius: 10,
            padding: 20,
            color: '#fff',
            display: 'flex',
            flexDirection: 'column',
            gap: 12
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: 8 }}>
            <span style={{ fontSize: '0.75rem', color: '#f59e0b', fontFamily: 'monospace', textTransform: 'uppercase' }}>Target Dossier</span>
            <button
              onClick={() => setSelectedTarget(null)}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
            >
              <X size={16} />
            </button>
          </div>

          <div>
            <div style={{ fontSize: '0.7rem', color: '#64748b', textTransform: 'uppercase' }}>Classification</div>
            <div style={{ fontSize: '1.05rem', fontWeight: 700, color: '#00f2fe' }}>
              {selectedTarget.properties.classification?.replace(/_/g, ' ')}
            </div>
          </div>

          <div>
            <div style={{ fontSize: '0.7rem', color: '#64748b', textTransform: 'uppercase' }}>Confidence</div>
            <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>
              {(selectedTarget.properties.confidence * 100).toFixed(1)}%
            </div>
          </div>

          <div>
            <div style={{ fontSize: '0.7rem', color: '#64748b', textTransform: 'uppercase' }}>Acquisition Timestamp</div>
            <div style={{ fontSize: '0.8rem', fontFamily: 'monospace', color: '#cbd5e1' }}>
              {selectedTarget.properties.detection_timestamp || selectedTarget.properties.detection_date}
            </div>
          </div>

          {selectedTarget.properties.area_sq_meters && (
            <div>
              <div style={{ fontSize: '0.7rem', color: '#64748b', textTransform: 'uppercase' }}>Geodesic Footprint Area</div>
              <div style={{ fontSize: '0.85rem', fontFamily: 'monospace' }}>
                {Math.round(selectedTarget.properties.area_sq_meters).toLocaleString()} m²
              </div>
            </div>
          )}

          <div>
            <div style={{ fontSize: '0.7rem', color: '#64748b', textTransform: 'uppercase' }}>Sensor Platform</div>
            <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              {selectedTarget.properties.sensor_source || 'Copernicus Sentinel-2'}
            </div>
          </div>
        </aside>
      )}

      {/* Bottom Temporal Timeline Scrubber */}
      <footer
        style={{
          position: 'absolute',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 'min(800px, calc(100vw - 32px))',
          zIndex: 10,
          background: 'rgba(16, 22, 34, 0.85)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(64, 90, 130, 0.3)',
          borderRadius: 12,
          padding: '14px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 16
        }}
      >
        <button
          onClick={() => setIsPlaying(!isPlaying)}
          style={{
            width: 38,
            height: 38,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #00f2fe, #4facfe)',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 0 12px rgba(0, 242, 254, 0.4)'
          }}
        >
          {isPlaying ? <Pause size={18} color="#000" /> : <Play size={18} color="#000" style={{ marginLeft: 2 }} />}
        </button>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontFamily: 'monospace' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Calendar size={14} color="#00f2fe" />
              <span style={{ color: '#00f2fe', fontWeight: 700 }}>{dateLabel}</span>
            </span>
            <span style={{ color: '#94a3b8' }}>
              Detected: <b>{filteredFeatures.length}</b> targets
            </span>
          </div>

          <input
            type="range"
            min={TIMELINE_MIN}
            max={TIMELINE_MAX}
            step={86400000} // Daily steps
            value={scrubberTime}
            onChange={e => {
              setIsPlaying(false);
              setScrubberTime(parseInt(e.target.value, 10));
            }}
            style={{ width: '100%', accentColor: '#00f2fe', cursor: 'pointer' }}
          />
        </div>
      </footer>
    </div>
  );
}
