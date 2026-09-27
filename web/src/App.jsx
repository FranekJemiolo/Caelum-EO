import React, { useState, useEffect, useMemo, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import Map from 'react-map-gl/maplibre';
import { Play, Pause, Shield, Radio, Activity, Eye, Layers, Calendar, ChevronRight, X } from 'lucide-react';
import { INITIAL_GEOINT_DATA } from './data/mockDetections.js';

// Initial viewport centered over Suwalki Strategic Corridor
const INITIAL_VIEW_STATE = {
  longitude: 23.23,
  latitude: 54.14,
  zoom: 11.2,
  pitch: 45,
  bearing: -15
};

// Tactical dark matter basemap style
const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

const CLASS_PALETTE = {
  Radar_Dome: { color: [245, 158, 11], hex: '#f59e0b', label: 'Radar Dome' },
  Logistics_Depot: { color: [16, 185, 129], hex: '#10b981', label: 'Logistics Depot' },
  Airfield_Runway: { color: [0, 242, 254], hex: '#00f2fe', label: 'Airfield Runway' },
  SAM_Battery_Site: { color: [244, 63, 94], hex: '#f43f5e', label: 'SAM Battery Site' },
  Hardened_Shelter: { color: [168, 85, 247], hex: '#a855f7', label: 'Hardened Shelter' },
  Naval_Pier_Berth: { color: [79, 172, 254], hex: '#4facfe', label: 'Naval Pier' },
  Fuel_Storage_Tank: { color: [234, 179, 8], hex: '#eab308', label: 'Fuel Storage' },
  Vehicle_Staging_Area: { color: [148, 163, 184], hex: '#94a3b8', label: 'Vehicle Staging' }
};

// Temporal scrubber range: May 1, 2026 to Sept 30, 2026
const TIMELINE_START = new Date('2026-05-01T00:00:00Z').getTime();
const TIMELINE_END = new Date('2026-09-30T23:59:59Z').getTime();

export default function App() {
  const [featureCollection, setFeatureCollection] = useState(INITIAL_GEOINT_DATA);
  const [activeClasses, setActiveClasses] = useState(new Set(Object.keys(CLASS_PALETTE)));
  const [minConfidence, setMinConfidence] = useState(0.80);
  const [currentScrubberTime, setCurrentScrubberTime] = useState(TIMELINE_END);
  const [isPlaying, setIsPlaying] = useState(false);
  const [selectedFeature, setSelectedFeature] = useState(null);

  // Attempt fetching from live FastAPI backend if available
  useEffect(() => {
    fetch('http://localhost:8000/api/detections')
      .then(res => res.json())
      .then(data => {
        if (data && data.features && data.features.length > 0) {
          setFeatureCollection(data);
        }
      })
      .catch(() => {
        // Standalone fallback: using rich built-in mock detections
      });
  }, []);

  // Temporal auto-play scrubber animation
  useEffect(() => {
    let timer;
    if (isPlaying) {
      timer = setInterval(() => {
        setCurrentScrubberTime(prev => {
          const step = 86400000 * 3; // Step forward 3 days per tick
          if (prev + step > TIMELINE_END) {
            return TIMELINE_START;
          }
          return prev + step;
        });
      }, 700);
    }
    return () => clearInterval(timer);
  }, [isPlaying]);

  const toggleClass = useCallback((cls) => {
    setActiveClasses(prev => {
      const next = new Set(prev);
      if (next.has(cls)) {
        next.delete(cls);
      } else {
        next.add(cls);
      }
      return next;
    });
  }, []);

  // Filter features by time scrubber, class visibility, and confidence threshold
  const filteredFeatures = useMemo(() => {
    if (!featureCollection || !featureCollection.features) return [];
    return featureCollection.features.filter(f => {
      const props = f.properties || {};
      const detectionTimestamp = new Date(props.detection_date).getTime();

      const timePass = detectionTimestamp <= currentScrubberTime;
      const classPass = activeClasses.has(props.classification);
      const confPass = (props.confidence ?? 1.0) >= minConfidence;

      return timePass && classPass && confPass;
    });
  }, [featureCollection, currentScrubberTime, activeClasses, minConfidence]);

  // Deck.gl GeoJsonLayer rendering vector intelligence
  const layers = [
    new GeoJsonLayer({
      id: 'geoint-infrastructure-layer',
      data: { type: 'FeatureCollection', features: filteredFeatures },
      pickable: true,
      stroked: true,
      filled: true,
      extruded: true,
      wireframe: true,
      lineWidthScale: 1,
      lineWidthMinPixels: 2,
      getFillColor: f => {
        const cls = f.properties.classification;
        const rgb = CLASS_PALETTE[cls]?.color || [200, 200, 200];
        return [...rgb, 180];
      },
      getLineColor: [255, 255, 255, 240],
      getElevation: f => (f.properties.confidence || 0.5) * 60,
      autoHighlight: true,
      highlightColor: [0, 242, 254, 200],
      onClick: info => {
        if (info.object) {
          setSelectedFeature(info.object);
        }
      }
    })
  ];

  const currentDateString = useMemo(() => {
    return new Date(currentScrubberTime).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  }, [currentScrubberTime]);

  return (
    <div className="app-container">
      {/* Tactical HUD Header */}
      <header className="tactical-hud-header glass-panel">
        <div className="hud-brand">
          <div className="hud-logo-icon">
            <Radio size={20} color="#000" />
          </div>
          <div>
            <h1 className="hud-title">CAELUM-EO</h1>
            <div className="hud-subtitle">Autonomous GEOINT Infrastructure Pipeline</div>
          </div>
        </div>

        <div className="hud-metrics">
          <div className="metric-pill">
            <span className="pulse-dot"></span>
            <span>STREAM: COP-CDSE S1/S2</span>
          </div>
          <div className="metric-pill">
            <Activity size={14} />
            <span>ACTIVE VECTORS: {filteredFeatures.length}</span>
          </div>
          <div className="metric-pill">
            <Shield size={14} />
            <span>ZONE: SUWALKI GAP</span>
          </div>
        </div>
      </header>

      {/* Main Map Visualizer */}
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller={true}
        layers={layers}
        getTooltip={({ object }) => {
          if (!object) return null;
          const p = object.properties;
          return {
            html: `
              <div style="font-family: var(--font-sans); padding: 8px; font-size: 12px; background: rgba(10,13,20,0.9); border: 1px solid rgba(0,242,254,0.4); border-radius: 6px; color: #fff;">
                <div style="font-weight: 700; color: #00f2fe; margin-bottom: 4px;">${p.classification.replace(/_/g, ' ')}</div>
                <div>Confidence: <b>${(p.confidence * 100).toFixed(1)}%</b></div>
                <div>Detected: ${new Date(p.detection_date).toLocaleDateString()}</div>
                <div>Sensor: ${p.source_imagery?.platform || 'Sentinel-2'}</div>
              </div>
            `
          };
        }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>

      {/* Left Sidebar: Controls & Layer Toggles */}
      <aside className="sidebar-panel glass-panel">
        <div className="panel-title">
          <Layers size={16} />
          <span>Infrastructure Classes</span>
        </div>

        <div className="class-toggle-list">
          {Object.entries(CLASS_PALETTE).map(([clsKey, item]) => {
            const count = (featureCollection?.features || []).filter(
              f => f.properties.classification === clsKey
            ).length;
            const isActive = activeClasses.has(clsKey);

            return (
              <div
                key={clsKey}
                className={`class-toggle-item ${isActive ? 'active' : ''}`}
                onClick={() => toggleClass(clsKey)}
              >
                <div className="class-info-left">
                  <span
                    className="class-color-indicator"
                    style={{ backgroundColor: item.hex, opacity: isActive ? 1 : 0.2 }}
                  />
                  <span className="class-label" style={{ color: isActive ? '#fff' : '#64748b' }}>
                    {item.label}
                  </span>
                </div>
                <span className="class-count">{count}</span>
              </div>
            );
          })}
        </div>

        <div className="slider-group">
          <div className="slider-header">
            <span style={{ color: 'var(--text-secondary)' }}>Min Confidence</span>
            <span style={{ color: 'var(--accent-cyan)' }}>{(minConfidence * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min="0.50"
            max="0.99"
            step="0.01"
            value={minConfidence}
            onChange={e => setMinConfidence(parseFloat(e.target.value))}
          />
        </div>
      </aside>

      {/* Selected Feature Intelligence Dossier */}
      {selectedFeature && (
        <aside className="inspection-drawer glass-panel">
          <div className="drawer-header">
            <span className="dossier-tag">Intelligence Target</span>
            <button className="close-btn" onClick={() => setSelectedFeature(null)}>
              <X size={18} />
            </button>
          </div>

          <div className="dossier-field">
            <span className="field-label">Classification</span>
            <span className="field-value" style={{ color: 'var(--accent-cyan)' }}>
              {selectedFeature.properties.classification.replace(/_/g, ' ')}
            </span>
          </div>

          <div className="dossier-field">
            <span className="field-label">Model Confidence</span>
            <span className="field-value">
              {(selectedFeature.properties.confidence * 100).toFixed(2)}%
            </span>
          </div>

          <div className="dossier-field">
            <span className="field-label">Acquisition Date</span>
            <span className="field-value">
              {new Date(selectedFeature.properties.detection_date).toUTCString()}
            </span>
          </div>

          <div className="dossier-field">
            <span className="field-label">Sensor Metadata</span>
            <pre className="field-code">
              {JSON.stringify(selectedFeature.properties.source_imagery, null, 2)}
            </pre>
          </div>

          {selectedFeature.properties.tactical_notes && (
            <div className="dossier-field">
              <span className="field-label">Tactical Assessment</span>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                {selectedFeature.properties.tactical_notes}
              </p>
            </div>
          )}
        </aside>
      )}

      {/* Bottom Temporal Timeline Scrubber */}
      <footer className="scrubber-panel glass-panel">
        <div className="scrubber-controls">
          <button
            className="play-button"
            onClick={() => setIsPlaying(!isPlaying)}
            title={isPlaying ? 'Pause Timeline' : 'Play Timeline'}
          >
            {isPlaying ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: 2 }} />}
          </button>

          <div className="scrubber-track-container">
            <div className="scrubber-meta">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Calendar size={14} color="var(--accent-cyan)" />
                <span className="current-date-badge">{currentDateString}</span>
              </span>
              <span>
                Active in View: <b>{filteredFeatures.length}</b> targets
              </span>
            </div>

            <input
              type="range"
              min={TIMELINE_START}
              max={TIMELINE_END}
              step={86400000} // Daily steps
              value={currentScrubberTime}
              onChange={e => {
                setIsPlaying(false);
                setCurrentScrubberTime(parseInt(e.target.value, 10));
              }}
            />
          </div>
        </div>
      </footer>
    </div>
  );
}
