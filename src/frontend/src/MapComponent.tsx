import React, { useState, useEffect, useMemo, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import Map from 'react-map-gl/maplibre';
import { Play, Pause, Radio, Calendar, X, Flame, Eye, CheckSquare } from 'lucide-react';

import { DetectionFeature, DetectionFeatureCollection, InfrastructureClass, ReviewPayload, ZoneSummary } from './types';
import { TriageHotlist } from './components/TriageHotlist';
import { MultiTemporalInspector } from './components/MultiTemporalInspector';
import { ReviewModal } from './components/ReviewModal';

// Suwalki Gap Strategic Surveillance Corridor Initial Viewport
const INITIAL_VIEW_STATE = {
  longitude: 23.23,
  latitude: 54.14,
  zoom: 11.2,
  pitch: 45,
  bearing: -15,
};

const DARK_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

// Classification color palette adhering strictly to Section 5.1 specification:
// Cyan = RADAR_DOME, Amber = RUNWAY_TAXIWAY, Purple = LOGISTICS_DEPOT,
// Crimson = UNKNOWN_STRUCTURE, Pink = DEFENSE_REVETMENT, Emerald = INDUSTRIAL_BUILDING
export const CLASSIFICATION_COLORS: Record<
  InfrastructureClass,
  { rgb: [number, number, number]; hex: string; label: string }
> = {
  RADAR_DOME: { rgb: [0, 242, 254], hex: '#00f2fe', label: 'Radar Dome' }, // Cyan
  RUNWAY_TAXIWAY: { rgb: [245, 158, 11], hex: '#f59e0b', label: 'Runway / Taxiway' }, // Amber
  LOGISTICS_DEPOT: { rgb: [168, 85, 247], hex: '#a855f7', label: 'Logistics Depot' }, // Purple
  DEFENSE_REVETMENT: { rgb: [236, 72, 153], hex: '#ec4899', label: 'Defense Revetment' }, // Pink
  INDUSTRIAL_BUILDING: { rgb: [16, 185, 129], hex: '#10b981', label: 'Industrial Building' }, // Emerald
  UNKNOWN_STRUCTURE: { rgb: [244, 63, 94], hex: '#f43f5e', label: 'Unknown Structure' }, // Crimson
};

// Seed Data for Offline Operation
const SEED_GEOINT_DATA: DetectionFeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      id: 'a1b2c3d4-e5f6-47a8-b901-23456789abcd',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[23.148, 54.118], [23.156, 54.118], [23.156, 54.126], [23.148, 54.126], [23.148, 54.118]],
        ],
      },
      properties: {
        id: 'a1b2c3d4-e5f6-47a8-b901-23456789abcd',
        classification: 'RADAR_DOME',
        confidence: 0.965,
        area_sq_meters: 3450.0,
        baseline_timestamp: '2026-05-15T08:30:00Z',
        detection_timestamp: '2026-05-15T08:30:00Z',
        sensor_source: 'Sentinel-2A-MSI-L2A',
        zone_id: 'ZONE-SUWALKI-CORRIDOR',
        review_status: 'PENDING_REVIEW',
        priority_score: 0.95,
      },
    },
    {
      type: 'Feature',
      id: 'b2c3d4e5-f6a7-48b9-c012-3456789abcde',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[23.18, 54.1], [23.21, 54.1], [23.21, 54.115], [23.18, 54.115], [23.18, 54.1]],
        ],
      },
      properties: {
        id: 'b2c3d4e5-f6a7-48b9-c012-3456789abcde',
        classification: 'LOGISTICS_DEPOT',
        confidence: 0.912,
        area_sq_meters: 15400.0,
        baseline_timestamp: '2026-05-15T08:30:00Z',
        detection_timestamp: '2026-06-02T11:15:00Z',
        sensor_source: 'Sentinel-2B-MSI-L2A',
        zone_id: 'ZONE-SUWALKI-CORRIDOR',
        review_status: 'PENDING_REVIEW',
        priority_score: 0.82,
      },
    },
    {
      type: 'Feature',
      id: 'c3d4e5f6-a7b8-49c0-d123-456789abcdef',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[23.28, 54.195], [23.355, 54.2], [23.35, 54.215], [23.275, 54.21], [23.28, 54.195]],
        ],
      },
      properties: {
        id: 'c3d4e5f6-a7b8-49c0-d123-456789abcdef',
        classification: 'RUNWAY_TAXIWAY',
        confidence: 0.984,
        area_sq_meters: 42000.0,
        baseline_timestamp: '2026-05-15T08:30:00Z',
        detection_timestamp: '2026-07-10T14:00:00Z',
        sensor_source: 'Sentinel-2A-MSI-L2A',
        zone_id: 'ZONE-SUWALKI-CORRIDOR',
        review_status: 'PENDING_REVIEW',
        priority_score: 0.98,
      },
    },
    {
      type: 'Feature',
      id: 'd4e5f6a7-b8c9-40d1-e234-56789abcdef0',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[23.22, 54.13], [23.238, 54.13], [23.238, 54.144], [23.22, 54.144], [23.22, 54.13]],
        ],
      },
      properties: {
        id: 'd4e5f6a7-b8c9-40d1-e234-56789abcdef0',
        classification: 'DEFENSE_REVETMENT',
        confidence: 0.941,
        area_sq_meters: 8900.0,
        baseline_timestamp: '2026-05-15T08:30:00Z',
        detection_timestamp: '2026-08-22T09:45:00Z',
        sensor_source: 'Sentinel-2B-MSI-L2A',
        zone_id: 'ZONE-SUWALKI-CORRIDOR',
        review_status: 'VERIFIED',
        priority_score: 0.75,
      },
    },
    {
      type: 'Feature',
      id: 'e5f6a7b8-c9d0-41e2-f345-6789abcdef01',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[23.19, 54.118], [23.208, 54.118], [23.208, 54.129], [23.19, 54.129], [23.19, 54.118]],
        ],
      },
      properties: {
        id: 'e5f6a7b8-c9d0-41e2-f345-6789abcdef01',
        classification: 'INDUSTRIAL_BUILDING',
        confidence: 0.893,
        area_sq_meters: 6700.0,
        baseline_timestamp: '2026-05-15T08:30:00Z',
        detection_timestamp: '2026-09-18T10:20:00Z',
        sensor_source: 'Sentinel-2A-MSI-L2A',
        zone_id: 'ZONE-SUWALKI-CORRIDOR',
        review_status: 'PENDING_REVIEW',
        priority_score: 0.65,
      },
    },
  ],
};

const TIMELINE_MIN = new Date('2026-05-01T00:00:00Z').getTime();
const TIMELINE_MAX = new Date('2026-09-30T23:59:59Z').getTime();

export default function MapComponent({ apiUrl = 'http://localhost:8000' }: { apiUrl?: string }) {
  const [data, setData] = useState<DetectionFeatureCollection>(SEED_GEOINT_DATA);
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [activeClasses, setActiveClasses] = useState<Set<string>>(
    new Set(Object.keys(CLASSIFICATION_COLORS))
  );
  const [showHotspots, setShowHotspots] = useState<boolean>(false);
  const [scrubberTime, setScrubberTime] = useState<number>(TIMELINE_MAX);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);

  // Modals & Panels State
  const [selectedTarget, setSelectedTarget] = useState<DetectionFeature | null>(null);
  const [inspectTarget, setInspectTarget] = useState<DetectionFeature | null>(null);
  const [reviewTarget, setReviewTarget] = useState<DetectionFeature | null>(null);
  const [isHotlistOpen, setIsHotlistOpen] = useState<boolean>(true);

  // Fetch live detections & zones
  useEffect(() => {
    fetch(`${apiUrl}/api/v1/detections`)
      .then((res) => res.json())
      .then((json) => {
        if (json && json.features && json.features.length > 0) {
          setData(json);
        }
      })
      .catch(() => {
        // Fallback to seed data
      });

    fetch(`${apiUrl}/api/v1/zones/summary`)
      .then((res) => res.json())
      .then((json) => {
        if (Array.isArray(json)) {
          setZones(json);
        }
      })
      .catch(() => {});
  }, [apiUrl]);

  // Automated temporal playback animation
  useEffect(() => {
    let interval: any;
    if (isPlaying) {
      interval = setInterval(() => {
        setScrubberTime((prev) => {
          const step = 86400000 * 3; // 3 days
          if (prev + step > TIMELINE_MAX) return TIMELINE_MIN;
          return prev + step;
        });
      }, 700);
    }
    return () => clearInterval(interval);
  }, [isPlaying]);

  const toggleCategory = useCallback((cls: string) => {
    setActiveClasses((prev) => {
      const next = new Set(prev);
      if (next.has(cls)) next.delete(cls);
      else next.add(cls);
      return next;
    });
  }, []);

  // Filter features by time scrubber and active categories
  const filteredFeatures = useMemo(() => {
    return (data.features || []).filter((f) => {
      const cls = f.properties?.classification;
      if (!activeClasses.has(cls)) return false;
      const ts = new Date(f.properties?.detection_timestamp || 0).getTime();
      return ts <= scrubberTime;
    });
  }, [data, activeClasses, scrubberTime]);

  // Camera FlyTo Animation on target selection
  const handleSelectTarget = useCallback((target: DetectionFeature) => {
    setSelectedTarget(target);
    const coords = target.geometry.coordinates[0];
    if (coords && coords.length > 0) {
      const avgLon = coords.reduce((acc, c) => acc + c[0], 0) / coords.length;
      const avgLat = coords.reduce((acc, c) => acc + c[1], 0) / coords.length;
      setViewState((prev) => ({
        ...prev,
        longitude: avgLon,
        latitude: avgLat,
        zoom: 13.5,
        pitch: 50,
      }));
    }
  }, []);

  // Submit Review Handler
  const handleSubmitReview = async (detectionId: string, payload: ReviewPayload) => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/detections/${detectionId}/review`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const updated = await res.json();
        // Update local state
        setData((prev) => ({
          ...prev,
          features: prev.features.map((f) =>
            f.id === detectionId
              ? {
                  ...f,
                  properties: {
                    ...f.properties,
                    review_status: updated.review_status,
                    verified_class: updated.verified_class,
                    priority_score: updated.priority_score,
                    reviewer_notes: updated.reviewer_notes,
                    reviewed_by: updated.reviewed_by,
                    reviewed_at: updated.reviewed_at,
                  },
                }
              : f
          ),
        }));
      }
    } catch (err) {
      console.error('Failed to submit review:', err);
    }
  };

  // Next Queue Item for spacebar navigation
  const handleNextQueueItem = () => {
    const pending = filteredFeatures.filter((f) => f.properties.review_status === 'PENDING_REVIEW');
    if (pending.length > 0) {
      const next = pending[0];
      handleSelectTarget(next);
      setReviewTarget(next);
    } else {
      setReviewTarget(null);
    }
  };

  // Deck.gl Layers
  const layers = useMemo(() => {
    const list: any[] = [];

    // 1. Regional Density / Zone Hotspot Choropleth Layer
    if (showHotspots && zones.length > 0) {
      const zoneFeatures = zones.map((z) => ({
        type: 'Feature',
        geometry: z.boundary,
        properties: z,
      }));

      list.push(
        new GeoJsonLayer({
          id: 'zone-hotspots-layer',
          data: { type: 'FeatureCollection', features: zoneFeatures },
          pickable: true,
          stroked: true,
          filled: true,
          lineWidthMinPixels: 2,
          getLineColor: [244, 63, 94, 200],
          getFillColor: (f: any) => {
            const count = f.properties.total_detections || 0;
            const alpha = Math.min(180, 40 + count * 35);
            return [244, 63, 94, alpha];
          },
          getLineWidth: 2,
        })
      );
    }

    // 2. Primary Bounding Box & Polygon Extraction Layer
    list.push(
      new GeoJsonLayer({
        id: 'geoint-detections-layer',
        data: { type: 'FeatureCollection', features: filteredFeatures },
        pickable: true,
        stroked: true,
        filled: true,
        extruded: true,
        wireframe: true,
        lineWidthMinPixels: 2,
        getElevation: (f: any) => (f.properties?.confidence || 0.5) * 80,
        getFillColor: (f: any) => {
          const cls = f.properties?.classification as InfrastructureClass;
          const isSelected = selectedTarget?.id === f.id;
          const base = CLASSIFICATION_COLORS[cls]?.rgb || [148, 163, 184];
          return isSelected ? [255, 255, 255, 220] : [...base, 140];
        },
        getLineColor: (f: any) => {
          const cls = f.properties?.classification as InfrastructureClass;
          const isSelected = selectedTarget?.id === f.id;
          const base = CLASSIFICATION_COLORS[cls]?.rgb || [148, 163, 184];
          return isSelected ? [255, 255, 255, 255] : [...base, 255];
        },
        getLineWidth: (f: any) => (selectedTarget?.id === f.id ? 4 : 2),
        onClick: (info: any) => {
          if (info.object) {
            handleSelectTarget(info.object);
          }
        },
      })
    );

    return list;
  }, [filteredFeatures, selectedTarget, showHotspots, zones, handleSelectTarget]);

  const dateLabel = new Date(scrubberTime).toISOString().slice(0, 10);

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-slate-950 font-sans select-none">
      {/* WebGL Deck.gl Map Canvas */}
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState }: any) => setViewState(viewState)}
        controller={true}
        layers={layers}
        getTooltip={({ object }: any) => {
          if (!object) return null;
          if (object.properties?.alert_level) {
            // Zone Tooltip
            const z = object.properties;
            return {
              html: `
                <div style="background:#0a0d14;color:#fff;padding:8px;border-radius:6px;border:1px solid #f43f5e;font-family:monospace;font-size:12px;">
                  <b style="color:#f43f5e;">${z.name}</b><br/>
                  Alert Level: <b>${z.alert_level}</b><br/>
                  Total Detections: <b>${z.total_detections}</b><br/>
                  High Priority: <b>${z.high_priority_count}</b>
                </div>
              `,
            };
          }
          const p = object.properties;
          const col = CLASSIFICATION_COLORS[p.classification as InfrastructureClass]?.hex || '#00f2fe';
          return {
            html: `
              <div style="background:#0a0d14;color:#fff;padding:8px 12px;border-radius:6px;border:1px solid ${col};font-family:monospace;font-size:12px;">
                <b style="color:${col};">${p.classification.replace(/_/g, ' ')}</b><br/>
                Confidence: <b>${(p.confidence * 100).toFixed(1)}%</b><br/>
                Detected: <b>${p.detection_timestamp?.slice(0, 10)}</b><br/>
                Area: <b>${p.area_sq_meters ? Math.round(p.area_sq_meters).toLocaleString() + ' m²' : 'N/A'}</b><br/>
                Priority: <b>P-${((p.priority_score || 0) * 100).toFixed(0)}</b>
              </div>
            `,
          };
        }}
      >
        <Map reuseMaps mapLib={import('maplibre-gl')} mapStyle={DARK_MAP_STYLE} />
      </DeckGL>

      {/* Floating Tactical HUD Panel (Top Left) */}
      <aside className="absolute top-4 left-4 z-10 w-72 bg-slate-950/90 border border-slate-800 backdrop-blur-xl rounded-xl p-4 shadow-2xl text-slate-100 flex flex-col gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-gradient-to-br from-cyan-400 to-blue-500 text-slate-950">
            <Radio size={18} />
          </div>
          <div>
            <h1 className="text-sm font-black tracking-widest text-cyan-400 font-mono">CAELUM-EO</h1>
            <div className="text-[10px] text-slate-400 font-mono">AUTONOMOUS GEOINT PIPELINE</div>
          </div>
        </div>

        {/* Dual Mode Layer Toggle */}
        <div className="flex items-center gap-2 pt-1 border-t border-slate-800">
          <button
            onClick={() => setShowHotspots((prev) => !prev)}
            className={`flex-1 py-1.5 px-2.5 rounded-lg text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-colors border ${
              showHotspots
                ? 'bg-rose-500/20 text-rose-300 border-rose-500/50 shadow-[0_0_12px_rgba(244,63,94,0.3)]'
                : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
            }`}
          >
            <Flame size={13} />
            Zone Hotspots
          </button>
        </div>

        {/* Infrastructure Categories Filter */}
        <div className="flex flex-col gap-1 pt-1 border-t border-slate-800">
          <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider mb-1">
            Infrastructure Classes
          </div>
          {(Object.entries(CLASSIFICATION_COLORS) as [InfrastructureClass, any][]).map(([key, item]) => {
            const count = (data.features || []).filter((f) => f.properties.classification === key).length;
            const active = activeClasses.has(key);
            return (
              <div
                key={key}
                onClick={() => toggleCategory(key)}
                className={`flex items-center justify-between px-2.5 py-1.5 rounded-md cursor-pointer text-xs font-mono transition-all border ${
                  active
                    ? 'bg-slate-900/90 border-slate-700 text-slate-200'
                    : 'bg-transparent border-transparent text-slate-500 hover:text-slate-400'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-sm"
                    style={{ backgroundColor: item.hex, opacity: active ? 1 : 0.2 }}
                  />
                  <span>{item.label}</span>
                </div>
                <span className="text-[11px] font-mono opacity-80">{count}</span>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Target Details Dossier Side Drawer (Left of Triage panel) */}
      {selectedTarget && (
        <aside className="absolute top-4 left-80 z-10 w-80 bg-slate-950/95 border border-slate-800 backdrop-blur-xl rounded-xl p-4 shadow-2xl text-slate-100 flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-[11px] font-mono font-bold text-amber-400 uppercase tracking-wider">
              Target Intelligence Dossier
            </span>
            <button
              onClick={() => setSelectedTarget(null)}
              className="p-1 rounded text-slate-400 hover:text-white transition-colors"
            >
              <X size={15} />
            </button>
          </div>

          <div>
            <div className="text-[10px] text-slate-500 font-mono uppercase">Classification</div>
            <div className="text-sm font-bold text-cyan-400 font-mono">
              {selectedTarget.properties.classification.replace(/_/g, ' ')}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div>
              <div className="text-[10px] text-slate-500 uppercase">Confidence</div>
              <div className="font-bold">{(selectedTarget.properties.confidence * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase">Priority</div>
              <div className="font-bold text-amber-400">
                P-{((selectedTarget.properties.priority_score || 0) * 100).toFixed(0)}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase">Surface Area</div>
              <div>
                {selectedTarget.properties.area_sq_meters
                  ? `${Math.round(selectedTarget.properties.area_sq_meters).toLocaleString()} m²`
                  : 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-slate-500 uppercase">Review State</div>
              <div className="text-emerald-400">{selectedTarget.properties.review_status}</div>
            </div>
          </div>

          {/* Action Buttons for Inspector & Labeling */}
          <div className="flex gap-2 pt-2 border-t border-slate-800">
            <button
              onClick={() => setInspectTarget(selectedTarget)}
              className="flex-1 py-1.5 px-2 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30 text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-colors"
            >
              <Eye size={13} />
              Inspector
            </button>
            <button
              onClick={() => setReviewTarget(selectedTarget)}
              className="flex-1 py-1.5 px-2 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30 text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-colors"
            >
              <CheckSquare size={13} />
              Review
            </button>
          </div>
        </aside>
      )}

      {/* Priority Triage Hotlist Drawer (Right) */}
      <TriageHotlist
        items={filteredFeatures}
        isOpen={isHotlistOpen}
        onToggle={() => setIsHotlistOpen((prev) => !prev)}
        onSelectTarget={handleSelectTarget}
        onInspect={(target) => {
          handleSelectTarget(target);
          setInspectTarget(target);
        }}
        selectedId={selectedTarget?.id || null}
      />

      {/* Multi-Temporal Image Comparison Inspector Modal */}
      {inspectTarget && (
        <MultiTemporalInspector
          feature={inspectTarget}
          onClose={() => setInspectTarget(null)}
          onOpenReview={(target) => {
            setInspectTarget(null);
            setReviewTarget(target);
          }}
          apiUrl={apiUrl}
        />
      )}

      {/* Human-in-the-Loop Reclassification Modal */}
      {reviewTarget && (
        <ReviewModal
          feature={reviewTarget}
          onClose={() => setReviewTarget(null)}
          onSubmitReview={handleSubmitReview}
          onNextQueueItem={handleNextQueueItem}
        />
      )}

      {/* Bottom Temporal Timeline Scrubber */}
      <footer className="absolute bottom-6 left-1/2 -translate-x-1/2 w-[min(820px,calc(100vw-32px))] z-10 bg-slate-950/90 backdrop-blur-xl border border-slate-800 rounded-2xl px-6 py-3.5 shadow-2xl flex items-center gap-4 text-slate-100">
        <button
          onClick={() => setIsPlaying(!isPlaying)}
          className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center text-slate-950 font-bold shadow-[0_0_15px_rgba(0,242,254,0.4)] hover:scale-105 transition-transform"
        >
          {isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
        </button>

        <div className="flex-1 flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs font-mono">
            <span className="flex items-center gap-1.5 text-cyan-400 font-bold">
              <Calendar size={14} />
              <span>{dateLabel}</span>
            </span>
            <span className="text-slate-400">
              Active: <b className="text-slate-200">{filteredFeatures.length}</b> anomalies
            </span>
          </div>

          <input
            type="range"
            min={TIMELINE_MIN}
            max={TIMELINE_MAX}
            step={86400000}
            value={scrubberTime}
            onChange={(e) => {
              setIsPlaying(false);
              setScrubberTime(parseInt(e.target.value, 10));
            }}
            className="w-full accent-cyan-400 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
          />
        </div>
      </footer>
    </div>
  );
}
