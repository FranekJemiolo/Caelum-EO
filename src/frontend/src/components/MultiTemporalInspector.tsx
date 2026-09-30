import React, { useState, useEffect, useRef } from "react";
import {
  X,
  Layers,
  Sun,
  Cloud,
  Calendar,
  Shield,
  Radio,
  History,
} from "lucide-react";
import { DetectionFeature } from "../types";
import { AuditTimeline } from "./AuditTimeline";
import { isDemoMode, getBaseUrl } from "../demoData";

interface MultiTemporalInspectorProps {
  feature: DetectionFeature | null;
  onClose: () => void;
  onOpenReview: (feature: DetectionFeature) => void;
  apiUrl?: string;
  titilerUrl?: string;
}

export const MultiTemporalInspector: React.FC<MultiTemporalInspectorProps> = ({
  feature,
  onClose,
  onOpenReview,
  apiUrl = "http://localhost:8000",
  titilerUrl = "http://localhost:8001",
}) => {
  const [activeTab, setActiveTab] = useState<"visual" | "audit">("visual");
  const [sliderPos, setSliderPos] = useState<number>(50); // Percentage 0 - 100
  const [showMask, setShowMask] = useState<boolean>(true);
  const [useTitiler, setUseTitiler] = useState<boolean>(() => !isDemoMode());
  const [titilerError, setTitilerError] = useState<boolean>(false);
  const [modality, setModality] = useState<"optical" | "sar" | "fused">(
    "optical",
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef<boolean>(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "m" || e.key === "M") {
        setShowMask((prev) => !prev);
      } else if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!feature) return null;

  const props = feature.properties;
  const detId = feature.id;
  const demoActive = isDemoMode();
  const base = getBaseUrl();
  const demoT0Url = `${base}demo-data/imagery/t0.webp`;
  const demoT1Url = `${base}demo-data/imagery/t1.webp`;
  const demoMaskUrl = `${base}demo-data/imagery/mask.webp`;

  const staticT0Url = demoActive
    ? demoT0Url
    : `${apiUrl}/api/v1/detections/${detId}/imagery/t0`;
  const staticT1Url = demoActive
    ? demoT1Url
    : `${apiUrl}/api/v1/detections/${detId}/imagery/t1`;
  const maskUrl = demoActive
    ? demoMaskUrl
    : `${apiUrl}/api/v1/detections/${detId}/imagery/mask`;

  // Compute dynamic TiTiler COG stream URLs if COG URI exists or dynamically crop via TiTiler
  const coords = feature.geometry?.coordinates?.[0] || [];
  const minX = coords.length ? Math.min(...coords.map((c) => c[0])) : 0;
  const minY = coords.length ? Math.min(...coords.map((c) => c[1])) : 0;
  const maxX = coords.length ? Math.max(...coords.map((c) => c[0])) : 0;
  const maxY = coords.length ? Math.max(...coords.map((c) => c[1])) : 0;

  const cogSourceT0 =
    props.stac_metadata?.baseline_cog ||
    `http://minio:9000/caelum-raw/sentinel2_t0_${detId}.tif`;
  const cogSourceT1 =
    props.stac_metadata?.detection_cog ||
    `http://minio:9000/caelum-raw/sentinel2_t1_${detId}.tif`;

  const titilerT0Url = `${titilerUrl}/cog/crop/${minX.toFixed(
    4,
  )},${minY.toFixed(4)},${maxX.toFixed(4)},${maxY.toFixed(
    4,
  )}.png?url=${encodeURIComponent(cogSourceT0)}`;
  const titilerT1Url = `${titilerUrl}/cog/crop/${minX.toFixed(
    4,
  )},${minY.toFixed(4)},${maxX.toFixed(4)},${maxY.toFixed(
    4,
  )}.png?url=${encodeURIComponent(cogSourceT1)}`;

  const activeT0Url = useTitiler && !titilerError ? titilerT0Url : staticT0Url;
  const activeT1Url = useTitiler && !titilerError ? titilerT1Url : staticT1Url;

  const handlePointerDown = () => {
    isDragging.current = true;
  };

  const handlePointerUp = () => {
    isDragging.current = false;
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="relative w-full max-w-4xl bg-slate-950 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header Bar */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Layers size={18} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100 font-mono tracking-wide">
                MULTI-TEMPORAL CHIP INSPECTOR
              </h2>
              <div className="text-xs text-slate-400 font-mono">
                TARGET ID: {detId} · {props.classification.replace(/_/g, " ")}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => onOpenReview(feature)}
              className="px-3.5 py-1.5 rounded-lg bg-cyan-500 text-slate-950 hover:bg-cyan-400 font-bold text-xs tracking-wider uppercase transition-colors shadow-[0_0_15px_rgba(0,242,254,0.3)]"
            >
              Triage & Label
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 bg-slate-900/40 font-mono text-xs">
          <button
            onClick={() => setActiveTab("visual")}
            className={`flex-1 py-2.5 px-4 flex items-center justify-center gap-2 border-b-2 font-bold transition-colors ${
              activeTab === "visual"
                ? "border-cyan-400 text-cyan-400 bg-cyan-950/20"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Layers size={14} />
            <span>Multi-Temporal Chip Comparison</span>
          </button>
          <button
            onClick={() => setActiveTab("audit")}
            className={`flex-1 py-2.5 px-4 flex items-center justify-center gap-2 border-b-2 font-bold transition-colors ${
              activeTab === "audit"
                ? "border-cyan-400 text-cyan-400 bg-cyan-950/20"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <History size={14} />
            <span>Audit History & Lifecycle Timeline</span>
          </button>
        </div>

        {activeTab === "audit" ? (
          <div className="p-6 flex-1 overflow-y-auto max-h-[70vh]">
            <AuditTimeline detectionId={detId} apiUrl={apiUrl} />
          </div>
        ) : (
          <>
            {/* Temporal Metadata Bar */}
            <div className="px-6 py-2.5 bg-slate-900/40 border-b border-slate-800/80 flex flex-wrap items-center justify-between text-xs font-mono text-slate-300 gap-4">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1.5 text-amber-400">
                  <Calendar size={14} />
                  <span>
                    T0 Baseline:{" "}
                    {props.baseline_timestamp?.slice(0, 10) || "2026-05-15"}
                  </span>
                </span>
                <span className="text-slate-600">➔</span>
                <span className="flex items-center gap-1.5 text-cyan-400">
                  <Calendar size={14} />
                  <span>
                    T1 Monitor:{" "}
                    {props.detection_timestamp?.slice(0, 10) || "2026-09-27"}
                  </span>
                </span>
              </div>

              <div className="flex items-center gap-4 text-slate-400">
                <span className="flex items-center gap-1">
                  <Cloud size={14} />
                  <span>
                    Cloud: {props.stac_metadata?.cloud_cover ?? "1.2"}%
                  </span>
                </span>
                <span className="flex items-center gap-1">
                  <Sun size={14} />
                  <span>Sun Azimuth: 142.8°</span>
                </span>
                <span className="flex items-center gap-1">
                  <Shield size={14} />
                  <span>Sensor: {props.sensor_source || "Sentinel-2A"}</span>
                </span>
              </div>
            </div>

            {/* Visual Swipe Comparison Viewport */}
            <div className="p-6 flex flex-col items-center justify-center flex-1 bg-slate-950/60 overflow-hidden">
              <div
                ref={containerRef}
                onPointerDown={handlePointerDown}
                onPointerUp={handlePointerUp}
                onPointerMove={handlePointerMove}
                className="relative w-full max-w-2xl aspect-video rounded-xl overflow-hidden border border-slate-700/80 select-none shadow-2xl cursor-ew-resize bg-slate-900"
              >
                {/* T1 Post-Change Satellite Image (Underneath) */}
                <img
                  src={activeT1Url}
                  alt="T1 Monitoring Pass"
                  onError={() => {
                    if (useTitiler && !titilerError) {
                      setTitilerError(true);
                    }
                  }}
                  className="absolute inset-0 w-full h-full object-cover pointer-events-none"
                />

                {/* Optional AI Change Mask Overlay */}
                {showMask && (
                  <img
                    src={maskUrl}
                    alt="AI Anomaly Mask"
                    className="absolute inset-0 w-full h-full object-cover pointer-events-none mix-blend-screen opacity-90 transition-opacity"
                  />
                )}

                {/* T0 Baseline Satellite Image (Clipped overlay) */}
                <div
                  className="absolute inset-0 overflow-hidden pointer-events-none"
                  style={{ width: `${sliderPos}%` }}
                >
                  <img
                    src={activeT0Url}
                    alt="T0 Baseline Pass"
                    onError={() => {
                      if (useTitiler && !titilerError) {
                        setTitilerError(true);
                      }
                    }}
                    className="absolute inset-0 w-full h-full object-cover max-w-none pointer-events-none"
                    style={{
                      width: containerRef.current?.clientWidth || "100%",
                    }}
                  />
                </div>

                {/* Vertical Divider Line with Tactical Handle */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 shadow-[0_0_12px_#00f2fe] pointer-events-none"
                  style={{ left: `${sliderPos}%` }}
                >
                  <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-slate-950 border-2 border-cyan-400 flex items-center justify-center shadow-lg text-cyan-400 text-[10px] font-mono font-bold">
                    ⮂
                  </div>
                </div>

                {/* Visual Overlays / Labels */}
                <div className="absolute bottom-3 left-3 px-2.5 py-1 rounded bg-black/70 backdrop-blur-md text-[11px] font-mono text-amber-400 border border-amber-500/30">
                  T0 BASELINE ({sliderPos.toFixed(0)}%)
                </div>
                <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded bg-black/70 backdrop-blur-md text-[11px] font-mono text-cyan-400 border border-cyan-500/30">
                  T1 POST-CHANGE
                </div>
              </div>

              {/* Interactive Controls Bar */}
              <div className="mt-4 flex flex-wrap items-center justify-between w-full max-w-2xl px-2 gap-3">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowMask((prev) => !prev)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold border transition-colors flex items-center gap-1.5 ${
                      showMask
                        ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-[0_0_10px_rgba(0,242,254,0.2)]"
                        : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
                    }`}
                  >
                    <Layers size={13} />
                    Mask Overlay (Key: M)
                  </button>

                  <button
                    onClick={() => {
                      setTitilerError(false);
                      setUseTitiler((prev) => !prev);
                    }}
                    title="Toggle dynamic Cloud-Optimized GeoTIFF raster stream from TiTiler vs static chip"
                    className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold border transition-colors flex items-center gap-1.5 ${
                      useTitiler && !titilerError
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                        : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
                    }`}
                  >
                    <Radio size={13} />
                    {useTitiler && !titilerError
                      ? "TiTiler COG Stream"
                      : "Static Chip Cache"}
                  </button>
                </div>

                {/* Version Two Multi-Modal Sensor Switcher */}
                <div className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-lg border border-slate-800 text-xs font-mono">
                  <button
                    onClick={() => setModality("optical")}
                    className={`px-2 py-1 rounded transition-colors ${
                      modality === "optical"
                        ? "bg-cyan-500 text-slate-950 font-bold"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Optical RGB
                  </button>
                  <button
                    onClick={() => setModality("sar")}
                    className={`px-2 py-1 rounded transition-colors ${
                      modality === "sar"
                        ? "bg-indigo-500 text-white font-bold"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    SAR VV/VH
                  </button>
                  <button
                    onClick={() => setModality("fused")}
                    className={`px-2 py-1 rounded transition-colors ${
                      modality === "fused"
                        ? "bg-purple-500 text-white font-bold"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Cross-Attention Fused
                  </button>
                </div>
              </div>

              {/* V2 Modality Badge */}
              {modality !== "optical" && (
                <div className="mt-2 text-[11px] font-mono text-indigo-400 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping" />
                  <span>
                    {modality === "sar"
                      ? "SENTINEL-1 C-BAND SAR DUAL-POL (VV / VH) SPECKLE-FILTERED BACKSCATTER (SIGMA-0 dB)"
                      : "PRITHVI-EO-2.0 CROSS-ATTENTION ATTENTION FUSED 8-CHANNEL TENSOR CUBE (OPTICAL + SAR)"}
                  </span>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
