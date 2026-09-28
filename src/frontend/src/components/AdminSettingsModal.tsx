import React, { useState, useEffect } from "react";
import {
  X,
  Sliders,
  Globe,
  Radio,
  Activity,
  Plus,
  Trash2,
  Save,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
  ShieldAlert,
  Send,
  HelpCircle,
} from "lucide-react";
import { AuthUser, GeofenceConfig, SystemConfig } from "../types";
import { authFetch } from "../auth";

interface AdminSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  apiUrl?: string;
}

const DEFAULT_GEOFENCES: GeofenceConfig[] = [
  {
    name: "Suwalki Corridor",
    bbox: [23.0, 54.0, 23.5, 54.4],
    description: "Primary transit choke-point between Poland and Lithuania",
  },
  {
    name: "Northern Frontier",
    bbox: [23.0, 54.4, 23.5, 54.7],
    description: "Border zone monitoring corridor",
  },
  {
    name: "Western Logistics",
    bbox: [22.6, 53.9, 23.0, 54.3],
    description: "Staging grounds and rail transshipment terminals",
  },
];

const PRESETS: GeofenceConfig[] = [
  {
    name: "Gotland Maritime Basin",
    bbox: [18.0, 57.0, 19.5, 58.0],
    description: "Central Baltic Sea naval approach",
  },
  {
    name: "Klaipeda Port & Air Approach",
    bbox: [20.9, 55.6, 21.3, 56.0],
    description: "Lithuanian deepwater port & naval airbase",
  },
  {
    name: "Brest Transshipment Junction",
    bbox: [23.5, 52.0, 24.2, 52.3],
    description: "Dual-gauge rail transshipment depot",
  },
];

export const AdminSettingsModal: React.FC<AdminSettingsModalProps> = ({
  isOpen,
  onClose,
  currentUser,
  apiUrl = "http://localhost:8000",
}) => {
  const [activeTab, setActiveTab] = useState<
    "geofences" | "inference" | "webhooks" | "observability"
  >("geofences");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  // Dynamic configurations
  const [geofences, setGeofences] =
    useState<GeofenceConfig[]>(DEFAULT_GEOFENCES);
  const [mlConfidenceThreshold, setMlConfidenceThreshold] =
    useState<number>(0.6);
  const [stacPollingInterval, setStacPollingInterval] = useState<number>(300);
  const [webhookUrl, setWebhookUrl] = useState<string>(
    "http://localhost:8000/api/v1/webhooks/alerts",
  );
  const [dlqTopic, setDlqTopic] = useState<string>("caelum.dlq");
  const [dlqItems, setDlqItems] = useState<any[]>([]);

  // Add geofence form state
  const [newGeofenceName, setNewGeofenceName] = useState("");
  const [minLon, setMinLon] = useState("23.00");
  const [minLat, setMinLat] = useState("54.00");
  const [maxLon, setMaxLon] = useState("23.50");
  const [maxLat, setMaxLat] = useState("54.40");

  // Webhook test state
  const [webhookTesting, setWebhookTesting] = useState(false);
  const [webhookTestResult, setWebhookTestResult] = useState<string | null>(
    null,
  );

  const isAdmin = currentUser?.role === "admin";

  useEffect(() => {
    if (isOpen && isAdmin) {
      loadConfigurations();
      loadDlqRecords();
    }
  }, [isOpen, isAdmin]);

  const loadConfigurations = async () => {
    setLoading(true);
    setStatusMessage(null);
    try {
      const res = await authFetch(`${apiUrl}/api/v1/admin/config`);
      if (res.ok) {
        const configs: SystemConfig[] = await res.json();
        configs.forEach((item) => {
          if (item.key === "target_geofences") {
            try {
              const parsed = JSON.parse(item.value);
              if (Array.isArray(parsed) && parsed.length > 0) {
                setGeofences(parsed);
              }
            } catch {
              // keep defaults if parse fails
            }
          } else if (item.key === "ml_confidence_threshold") {
            const val = parseFloat(item.value);
            if (!isNaN(val)) setMlConfidenceThreshold(val);
          } else if (item.key === "stac_polling_interval_seconds") {
            const val = parseInt(item.value, 10);
            if (!isNaN(val)) setStacPollingInterval(val);
          } else if (item.key === "webhook_url") {
            setWebhookUrl(item.value);
          } else if (item.key === "dlq_topic") {
            setDlqTopic(item.value);
          }
        });
      }
    } catch (err: any) {
      console.warn("Failed loading configs from API, using defaults:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadDlqRecords = async () => {
    try {
      const res = await authFetch(`${apiUrl}/api/v1/ops/dlq?limit=10`);
      if (res.ok) {
        const data = await res.json();
        setDlqItems(data.items || []);
      }
    } catch {
      // offline fallback
    }
  };

  const saveConfig = async (
    key: string,
    value: string,
    description: string,
  ) => {
    setSaving(true);
    setStatusMessage(null);
    try {
      const res = await authFetch(`${apiUrl}/api/v1/admin/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, value, description }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to update configuration.");
      }
      setStatusMessage({
        type: "success",
        text: `Configuration '${key}' saved successfully to PostGIS!`,
      });
    } catch (err: any) {
      setStatusMessage({
        type: "error",
        text: err.message || "Failed saving configuration.",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveGeofences = () => {
    saveConfig(
      "target_geofences",
      JSON.stringify(geofences),
      "Target geographic bounding boxes (geofences) actively polled by STAC collectors",
    );
  };

  const handleSaveInference = async () => {
    setSaving(true);
    setStatusMessage(null);
    try {
      await authFetch(`${apiUrl}/api/v1/admin/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: "ml_confidence_threshold",
          value: mlConfidenceThreshold.toFixed(2),
          description:
            "Minimum inference confidence score required to ingest detection into intelligence store",
        }),
      });
      await authFetch(`${apiUrl}/api/v1/admin/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: "stac_polling_interval_seconds",
          value: stacPollingInterval.toString(),
          description: "STAC catalog ingestion polling frequency in seconds",
        }),
      });
      setStatusMessage({
        type: "success",
        text: "Inference parameters updated successfully in PostGIS!",
      });
    } catch (err: any) {
      setStatusMessage({
        type: "error",
        text: err.message || "Failed saving inference configuration.",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveWebhook = () => {
    saveConfig(
      "webhook_url",
      webhookUrl,
      "Local webhook endpoint for critical GEOINT triage alerts",
    );
  };

  const handleTestWebhook = async () => {
    setWebhookTesting(true);
    setWebhookTestResult(null);
    try {
      const res = await authFetch(`${apiUrl}/api/v1/webhooks/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: "PING_TEST",
          timestamp: new Date().toISOString(),
          operator: currentUser?.username || "admin",
          target_url: webhookUrl,
          message: "Air-Gapped Webhook Integration Test from Project Caelum-EO",
        }),
      });
      if (res.ok) {
        setWebhookTestResult("Webhook ping succeeded (HTTP 200/202).");
      } else {
        setWebhookTestResult(`Webhook ping returned status: ${res.status}`);
      }
    } catch (err: any) {
      setWebhookTestResult(
        `Webhook dispatch error: ${err.message || "Network error"}`,
      );
    } finally {
      setWebhookTesting(false);
    }
  };

  const handleAddGeofence = () => {
    if (!newGeofenceName.trim()) return;
    const w = parseFloat(minLon);
    const s = parseFloat(minLat);
    const e = parseFloat(maxLon);
    const n = parseFloat(maxLat);
    if (isNaN(w) || isNaN(s) || isNaN(e) || isNaN(n)) return;

    const newGf: GeofenceConfig = {
      name: newGeofenceName.trim(),
      bbox: [w, s, e, n],
      description: `Active bbox [${w}, ${s}, ${e}, ${n}]`,
    };
    setGeofences([...geofences, newGf]);
    setNewGeofenceName("");
  };

  const handleRemoveGeofence = (index: number) => {
    setGeofences(geofences.filter((_, i) => i !== index));
  };

  const handleApplyPreset = (preset: GeofenceConfig) => {
    if (!geofences.some((g) => g.name === preset.name)) {
      setGeofences([...geofences, preset]);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/40">
              <Sliders size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-100 font-mono tracking-wide">
                  SYSTEM CONFIGURATION & ADMIN CONSOLE
                </h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  TOP SECRET // IT ADMIN
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Dynamic air-gapped configuration store • Changes apply
                immediately without container restarts
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Access Verification */}
        {!isAdmin ? (
          <div className="p-8 text-center flex flex-col items-center justify-center gap-4">
            <ShieldAlert size={48} className="text-rose-400 animate-pulse" />
            <h3 className="text-lg font-bold font-mono text-slate-200">
              ACCESS RESTRICTED: INSUFFICIENT SECURITY CLEARANCE
            </h3>
            <p className="text-sm text-slate-400 font-mono max-w-md">
              Only operators with the <b>admin</b> role can modify dynamic
              system parameters, geofences, and observability configurations.
            </p>
            <button
              onClick={onClose}
              className="mt-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono rounded-lg"
            >
              Return to Tactical Map
            </button>
          </div>
        ) : (
          <>
            {/* Status notification banner */}
            {statusMessage && (
              <div
                className={`px-6 py-2.5 text-xs font-mono flex items-center gap-2 border-b ${
                  statusMessage.type === "success"
                    ? "bg-emerald-950/60 border-emerald-800/80 text-emerald-300"
                    : "bg-rose-950/60 border-rose-800/80 text-rose-300"
                }`}
              >
                {statusMessage.type === "success" ? (
                  <CheckCircle2 size={15} />
                ) : (
                  <AlertTriangle size={15} />
                )}
                <span>{statusMessage.text}</span>
              </div>
            )}

            {/* Navigation Tabs */}
            <div className="flex border-b border-slate-800 bg-slate-950/40 px-6 pt-2 gap-1 text-xs font-mono">
              <button
                onClick={() => setActiveTab("geofences")}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-t-lg font-bold transition-colors border-t border-x ${
                  activeTab === "geofences"
                    ? "bg-slate-900 border-slate-700 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                }`}
              >
                <Globe size={14} />
                Target Geofences (STAC)
                <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-slate-800 text-cyan-300">
                  {geofences.length}
                </span>
              </button>

              <button
                onClick={() => setActiveTab("inference")}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-t-lg font-bold transition-colors border-t border-x ${
                  activeTab === "inference"
                    ? "bg-slate-900 border-slate-700 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                }`}
              >
                <Sliders size={14} />
                Inference & Models
              </button>

              <button
                onClick={() => setActiveTab("webhooks")}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-t-lg font-bold transition-colors border-t border-x ${
                  activeTab === "webhooks"
                    ? "bg-slate-900 border-slate-700 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                }`}
              >
                <Radio size={14} />
                Alert Webhooks
              </button>

              <button
                onClick={() => setActiveTab("observability")}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-t-lg font-bold transition-colors border-t border-x ${
                  activeTab === "observability"
                    ? "bg-slate-900 border-slate-700 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                }`}
              >
                <Activity size={14} />
                Observability & DLQ
              </button>
            </div>

            {/* Tab Contents */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* TAB 1: GEOFENCES */}
              {activeTab === "geofences" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
                        <span>Active STAC Target Geofences</span>
                        <span className="text-[10px] text-slate-400 font-normal">
                          (Fetched by Python STAC poller on every cycle)
                        </span>
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Add or remove bounding boxes [min_lon, min_lat, max_lon,
                        max_lat] in EPSG:4326.
                      </p>
                    </div>
                    <button
                      onClick={handleSaveGeofences}
                      disabled={saving}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-mono text-xs font-bold rounded-lg shadow-md transition-colors disabled:opacity-50"
                    >
                      <Save size={14} />
                      {saving ? "Saving..." : "Save Geofences to DB"}
                    </button>
                  </div>

                  {/* Geofences List */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {geofences.map((gf, idx) => (
                      <div
                        key={idx}
                        className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex items-start justify-between gap-3 group hover:border-slate-700 transition-colors"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                            <span className="font-mono font-bold text-xs text-slate-200">
                              {gf.name}
                            </span>
                          </div>
                          <div className="text-[11px] font-mono text-slate-400">
                            BBOX: [
                            <span className="text-cyan-300">
                              {gf.bbox.map((v) => v.toFixed(2)).join(", ")}
                            </span>
                            ]
                          </div>
                          {gf.description && (
                            <div className="text-[10px] text-slate-500">
                              {gf.description}
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => handleRemoveGeofence(idx)}
                          title="Remove Geofence"
                          className="p-1.5 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Add New Geofence Form */}
                  <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-3">
                    <h4 className="text-xs font-mono font-bold text-slate-300 flex items-center gap-1.5">
                      <Plus size={14} className="text-cyan-400" />
                      Add Target Geographic Bounding Box
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
                      <div className="md:col-span-2">
                        <label className="text-[10px] font-mono text-slate-400 block mb-1">
                          ZONE NAME
                        </label>
                        <input
                          type="text"
                          placeholder="e.g. Suwalki Gap East"
                          value={newGeofenceName}
                          onChange={(e) => setNewGeofenceName(e.target.value)}
                          className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-slate-400 block mb-1">
                          MIN LON (W)
                        </label>
                        <input
                          type="text"
                          value={minLon}
                          onChange={(e) => setMinLon(e.target.value)}
                          className="w-full px-2 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-400"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-slate-400 block mb-1">
                          MIN LAT (S)
                        </label>
                        <input
                          type="text"
                          value={minLat}
                          onChange={(e) => setMinLat(e.target.value)}
                          className="w-full px-2 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-400"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-slate-400 block mb-1">
                          MAX LON (E)
                        </label>
                        <input
                          type="text"
                          value={maxLon}
                          onChange={(e) => setMaxLon(e.target.value)}
                          className="w-full px-2 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-400"
                        />
                      </div>
                    </div>
                    <div className="flex items-center justify-between pt-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-mono text-slate-500">
                          Quick Presets:
                        </span>
                        {PRESETS.map((p, i) => (
                          <button
                            key={i}
                            onClick={() => handleApplyPreset(p)}
                            className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                          >
                            + {p.name}
                          </button>
                        ))}
                      </div>
                      <button
                        onClick={handleAddGeofence}
                        disabled={!newGeofenceName.trim()}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-300 font-mono text-xs font-bold rounded-lg border border-cyan-500/30 transition-colors disabled:opacity-40"
                      >
                        Add to Geofence List
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: INFERENCE & MODELS */}
              {activeTab === "inference" && (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
                      <span>Neural Inference & Detection Filtering</span>
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Configure live detection sensitivity and ingest cadence
                      without restarting ML worker containers.
                    </p>
                  </div>

                  {/* Confidence Slider Card */}
                  <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <label className="text-xs font-mono font-bold text-slate-200">
                          ML Confidence Ingestion Threshold
                        </label>
                        <p className="text-[11px] text-slate-400">
                          Minimum model certainty score required to accept
                          inferred anomalies into the database.
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
                            mlConfidenceThreshold >= 0.8
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                              : mlConfidenceThreshold >= 0.6
                                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                                : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                          }`}
                        >
                          {(mlConfidenceThreshold * 100).toFixed(0)}% (
                          {mlConfidenceThreshold.toFixed(2)})
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <input
                        type="range"
                        min="0.10"
                        max="0.95"
                        step="0.05"
                        value={mlConfidenceThreshold}
                        onChange={(e) =>
                          setMlConfidenceThreshold(parseFloat(e.target.value))
                        }
                        className="w-full accent-cyan-400 bg-slate-800 rounded-lg cursor-pointer h-2"
                      />
                      <div className="flex justify-between text-[10px] font-mono text-slate-500">
                        <span>
                          0.10 (Max Ingestion / High Potential False Positives)
                        </span>
                        <span>0.60 (Standard Balanced)</span>
                        <span>0.85 (High Precision / Low Noise)</span>
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 flex items-start gap-2.5 text-xs font-mono text-slate-300">
                      <HelpCircle
                        size={16}
                        className="text-cyan-400 shrink-0 mt-0.5"
                      />
                      <div>
                        Adjusting this value to <b>0.85</b> filters out fleeting
                        agricultural and cloud edge variations, restricting
                        alerts to high-confidence structural military
                        build-outs.
                      </div>
                    </div>
                  </div>

                  {/* STAC Polling Interval */}
                  <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <label className="text-xs font-mono font-bold text-slate-200">
                          STAC Catalog Polling Cadence (Seconds)
                        </label>
                        <p className="text-[11px] text-slate-400">
                          Frequency at which the STAC worker polls the
                          Copernicus CDSE catalog for new acquisitions.
                        </p>
                      </div>
                      <input
                        type="number"
                        min="60"
                        max="86400"
                        step="60"
                        value={stacPollingInterval}
                        onChange={(e) =>
                          setStacPollingInterval(
                            parseInt(e.target.value, 10) || 300,
                          )
                        }
                        className="w-28 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-cyan-300 text-right focus:outline-none focus:border-cyan-400"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <button
                      onClick={handleSaveInference}
                      disabled={saving}
                      className="flex items-center gap-1.5 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-mono text-xs font-bold rounded-lg shadow-md transition-colors disabled:opacity-50"
                    >
                      <Save size={14} />
                      {saving
                        ? "Committing Parameters..."
                        : "Save Inference Parameters"}
                    </button>
                  </div>
                </div>
              )}

              {/* TAB 3: WEBHOOKS */}
              {activeTab === "webhooks" && (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
                      <span>Tactical Webhook Alert Dispatch</span>
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Configure local network webhooks for SIEM and automated
                      high-priority alert dispatching.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-mono font-bold text-slate-200">
                        Local Webhook URL Endpoint
                      </label>
                      <input
                        type="url"
                        value={webhookUrl}
                        onChange={(e) => setWebhookUrl(e.target.value)}
                        placeholder="http://localhost:8000/api/v1/webhooks/alerts"
                        className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-400"
                      />
                      <p className="text-[10px] text-slate-500 font-mono">
                        Air-gapped constraint: Must resolve within the local
                        enclave / container bridge network.
                      </p>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <button
                        onClick={handleTestWebhook}
                        disabled={webhookTesting}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-mono text-xs rounded-lg border border-slate-700 transition-colors disabled:opacity-50"
                      >
                        <Send size={13} className="text-cyan-400" />
                        {webhookTesting
                          ? "Testing Dispatch..."
                          : "Send Test Alert Ping"}
                      </button>

                      <button
                        onClick={handleSaveWebhook}
                        disabled={saving}
                        className="flex items-center gap-1.5 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-mono text-xs font-bold rounded-lg shadow-md transition-colors disabled:opacity-50"
                      >
                        <Save size={14} />
                        {saving ? "Saving..." : "Save Webhook URL"}
                      </button>
                    </div>

                    {webhookTestResult && (
                      <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 font-mono text-xs text-cyan-300">
                        {webhookTestResult}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 4: OBSERVABILITY & DLQ */}
              {activeTab === "observability" && (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
                      <span>On-Premises Observability Stack & DLQ</span>
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Air-gapped health metrics, Prometheus scrapers, and Dead
                      Letter Queue inspection.
                    </p>
                  </div>

                  {/* Observability Services Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-bold text-slate-300">
                          Prometheus Server
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          ONLINE :9090
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 font-mono">
                        Scraping API (/metrics), Kafka workers, Redpanda, MinIO.
                      </p>
                      <a
                        href="http://localhost:9090"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-400 hover:underline pt-1"
                      >
                        Open Prometheus Web UI <ExternalLink size={11} />
                      </a>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-bold text-slate-300">
                          Grafana Dashboards
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          PORT :3002
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 font-mono">
                        Auto-provisioned Caelum-EO Enterprise Overview
                        dashboard.
                      </p>
                      <a
                        href="http://localhost:3002"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-400 hover:underline pt-1"
                      >
                        Open Grafana Dashboard <ExternalLink size={11} />
                      </a>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-bold text-slate-300">
                          Dead Letter Queue
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                          TOPIC: {dlqTopic}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 font-mono">
                        Captures corrupted raster tiles & model OOM failures.
                      </p>
                      <span className="text-[11px] font-mono text-slate-400 block pt-1">
                        Active DLQ records: <b>{dlqItems.length}</b>
                      </span>
                    </div>
                  </div>

                  {/* DLQ Recent Failures Inspection */}
                  <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-mono font-bold text-slate-200 flex items-center gap-1.5">
                        <AlertTriangle size={14} className="text-amber-400" />
                        Dead Letter Queue (DLQ) Incident Ledger
                      </h4>
                      <button
                        onClick={loadDlqRecords}
                        className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
                        title="Refresh DLQ"
                      >
                        <RefreshCw size={13} />
                      </button>
                    </div>

                    {dlqItems.length === 0 ? (
                      <div className="py-6 text-center text-xs font-mono text-slate-500 bg-slate-900/50 rounded-lg border border-slate-800/80">
                        Zero unhandled raster or OOM errors detected. Pipeline
                        operating normally.
                      </div>
                    ) : (
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {dlqItems.map((item, i) => (
                          <div
                            key={i}
                            className="p-2.5 rounded bg-slate-900 border border-rose-900/40 text-xs font-mono space-y-1"
                          >
                            <div className="flex items-center justify-between text-rose-300">
                              <span className="font-bold">
                                {item.error_type || "PipelineException"}
                              </span>
                              <span className="text-[10px] text-slate-500">
                                {item.timestamp}
                              </span>
                            </div>
                            <div className="text-[11px] text-slate-400">
                              {item.error_message}
                            </div>
                            <div className="text-[10px] text-slate-600">
                              Topic: {item.failed_topic}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between px-6 py-3 border-t border-slate-800 bg-slate-950/80 text-xs font-mono">
              <div className="text-slate-500">
                Logged in as:{" "}
                <b className="text-slate-300">{currentUser.username}</b> (
                {currentUser.role})
              </div>
              <button
                onClick={onClose}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-mono text-xs rounded-lg transition-colors"
              >
                Close Console
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
