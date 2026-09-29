import React, { useEffect, useRef, useState } from "react";
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  Title,
  CategoryScale,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import {
  TrendingUp,
  X,
  Layers,
  Activity,
  Calendar,
  RefreshCw,
  Building,
} from "lucide-react";
import { authFetch } from "../auth";

// Register necessary Chart.js controllers and elements
Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  Title,
  CategoryScale,
  Tooltip,
  Legend,
  Filler
);

interface VelocityPoint {
  timestamp: string;
  cumulative_area_sq_m: number;
  expansion_rate_sq_m_per_day: number;
}

interface VelocityClassMetrics {
  classification: string;
  current_area_sq_m: number;
  expansion_rate_sq_m_per_day: number;
  total_detections: number;
  timeline: VelocityPoint[];
}

interface VelocityData {
  zone_id: string | null;
  total_area_sq_m: number;
  mean_velocity_sq_m_per_day: number;
  classes: VelocityClassMetrics[];
}

interface VelocityModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiUrl?: string;
  initialZone?: string | null;
}

const CLASS_COLORS: Record<string, { stroke: string; fill: string }> = {
  LOGISTICS_DEPOT: {
    stroke: "#00F2FE", // Cyan
    fill: "rgba(0, 242, 254, 0.12)",
  },
  RADAR_DOME: {
    stroke: "#10B981", // Emerald
    fill: "rgba(16, 185, 129, 0.12)",
  },
  SAM_SITE: {
    stroke: "#F59E0B", // Amber
    fill: "rgba(245, 158, 11, 0.12)",
  },
  DEFENSE_REVETMENT: {
    stroke: "#F43F5E", // Rose
    fill: "rgba(244, 63, 94, 0.12)",
  },
  INDUSTRIAL_BUILDING: {
    stroke: "#8B5CF6", // Purple
    fill: "rgba(139, 92, 246, 0.12)",
  },
};

export const VelocityModal: React.FC<VelocityModalProps> = ({
  isOpen,
  onClose,
  apiUrl = "http://localhost:8000",
  initialZone = null,
}) => {
  const [data, setData] = useState<VelocityData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedZone, setSelectedZone] = useState<string>(initialZone || "ALL");
  const [lookbackMonths, setLookbackMonths] = useState<number>(6);
  const [activeClasses, setActiveClasses] = useState<Record<string, boolean>>({});

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstanceRef = useRef<Chart | null>(null);

  const fetchVelocity = async () => {
    setLoading(true);
    try {
      const zoneParam = selectedZone === "ALL" ? "" : `&zone_id=${encodeURIComponent(selectedZone)}`;
      const res = await authFetch(
        `${apiUrl}/api/v1/analytics/velocity?months_lookback=${lookbackMonths}${zoneParam}`
      );
      if (res.ok) {
        const json: VelocityData = await res.json();
        setData(json);

        // Initialize all active classes to true if unset
        const toggles: Record<string, boolean> = {};
        json.classes.forEach((c) => {
          toggles[c.classification] = true;
        });
        setActiveClasses(toggles);
      }
    } catch (err) {
      console.error("Failed fetching velocity metrics:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchVelocity();
    }
  }, [isOpen, selectedZone, lookbackMonths]);

  // Render / Update Chart.js Instance
  useEffect(() => {
    if (!canvasRef.current || !data || data.classes.length === 0) return;

    if (chartInstanceRef.current) {
      chartInstanceRef.current.destroy();
    }

    // Collect all timestamps from the first class with points
    const labels = data.classes[0]?.timeline.map((p) => p.timestamp) || [];

    const datasets = data.classes
      .filter((c) => activeClasses[c.classification] !== false)
      .map((c) => {
        const color = CLASS_COLORS[c.classification] || {
          stroke: "#94A3B8",
          fill: "rgba(148, 163, 184, 0.1)",
        };
        return {
          label: c.classification.replace(/_/g, " "),
          data: c.timeline.map((p) => p.cumulative_area_sq_m),
          borderColor: color.stroke,
          backgroundColor: color.fill,
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: color.stroke,
          pointBorderColor: "#020617",
          pointBorderWidth: 1.5,
        };
      });

    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    chartInstanceRef.current = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            backgroundColor: "rgba(2, 6, 23, 0.92)",
            borderColor: "rgba(51, 65, 85, 0.8)",
            borderWidth: 1,
            titleColor: "#94A3B8",
            titleFont: { family: "monospace", size: 11 },
            bodyFont: { family: "monospace", size: 12 },
            padding: 10,
            callbacks: {
              label: (context) => {
                const label = context.dataset.label || "";
                const val = (context.parsed.y || 0).toLocaleString();
                return ` ${label}: ${val} m²`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: {
              color: "rgba(30, 41, 59, 0.5)",
            },
            ticks: {
              color: "#64748B",
              font: { family: "monospace", size: 10 },
              maxRotation: 0,
            },
          },
          y: {
            grid: {
              color: "rgba(30, 41, 59, 0.5)",
            },
            ticks: {
              color: "#64748B",
              font: { family: "monospace", size: 10 },
              callback: (value) => `${Number(value).toLocaleString()} m²`,
            },
          },
        },
      },
    });

    return () => {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.destroy();
        chartInstanceRef.current = null;
      }
    };
  }, [data, activeClasses]);

  if (!isOpen) return null;

  const toggleClass = (className: string) => {
    setActiveClasses((prev) => ({
      ...prev,
      [className]: !prev[className],
    }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="relative w-full max-w-5xl bg-slate-900/95 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <header className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-[0_0_12px_rgba(0,242,254,0.3)]">
              <TrendingUp size={18} />
            </div>
            <div>
              <h2 className="text-base font-bold font-mono text-slate-100 flex items-center gap-2">
                Construction Velocity & Pattern of Life (PoL)
                <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/80">
                  d(Area)/dt
                </span>
              </h2>
              <p className="text-xs text-slate-400 font-mono">
                PostGIS temporal window derivatives of adversary infrastructure expansion
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchVelocity}
              disabled={loading}
              title="Refresh Analytics"
              className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-800 transition-colors"
            >
              <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* Filter Controls Bar */}
        <div className="px-6 py-3 border-b border-slate-800 bg-slate-950/30 flex flex-wrap items-center justify-between gap-4 font-mono text-xs">
          <div className="flex items-center gap-3">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Layers size={13} /> SECTOR:
            </span>
            <select
              value={selectedZone}
              onChange={(e) => setSelectedZone(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-200 rounded-lg px-2.5 py-1 focus:outline-none focus:border-cyan-500"
            >
              <option value="ALL">All Monitored Theaters</option>
              <option value="suwalki_corridor">Suwalki Strategic Corridor</option>
              <option value="kaliningrad_border">Kaliningrad Frontier Vector</option>
              <option value="gotland_deep">Gotland Baltic Sector</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Calendar size={13} /> TIMELINE:
            </span>
            {[3, 6, 12].map((m) => (
              <button
                key={m}
                onClick={() => setLookbackMonths(m)}
                className={`px-2.5 py-1 rounded-lg border transition-colors ${
                  lookbackMonths === m
                    ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-[0_0_8px_rgba(0,242,254,0.3)]"
                    : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
                }`}
              >
                {m}M
              </button>
            ))}
          </div>
        </div>

        {/* Analytics Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {/* Key Metrics KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col justify-between">
              <div className="text-[11px] font-mono uppercase text-slate-400 flex items-center justify-between">
                <span>Total Expansion Footprint</span>
                <Building size={14} className="text-cyan-400" />
              </div>
              <div className="text-2xl font-bold font-mono text-cyan-300 mt-2">
                {data ? `${Math.round(data.total_area_sq_m).toLocaleString()} m²` : "..."}
              </div>
              <div className="text-[10px] font-mono text-slate-500 mt-1">
                Cumulative footprint across {data?.classes.length || 0} facility classes
              </div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col justify-between">
              <div className="text-[11px] font-mono uppercase text-slate-400 flex items-center justify-between">
                <span>Mean Expansion Velocity</span>
                <Activity size={14} className="text-emerald-400" />
              </div>
              <div className="text-2xl font-bold font-mono text-emerald-300 mt-2">
                {data ? `${data.mean_velocity_sq_m_per_day.toLocaleString()} m²/day` : "..."}
              </div>
              <div className="text-[10px] font-mono text-slate-500 mt-1">
                Rate of physical structure expansion over {lookbackMonths}-month window
              </div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col justify-between">
              <div className="text-[11px] font-mono uppercase text-slate-400 flex items-center justify-between">
                <span>Fastest Growing Class</span>
                <TrendingUp size={14} className="text-amber-400" />
              </div>
              <div className="text-lg font-bold font-mono text-amber-300 mt-2 truncate">
                {data?.classes && data.classes.length > 0
                  ? [...data.classes].sort(
                      (a, b) => b.expansion_rate_sq_m_per_day - a.expansion_rate_sq_m_per_day
                    )[0]?.classification.replace(/_/g, " ")
                  : "N/A"}
              </div>
              <div className="text-[10px] font-mono text-slate-500 mt-1">
                Highest first-derivative velocity indicator
              </div>
            </div>
          </div>

          {/* Interactive Class Toggles */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs font-mono text-slate-400 mr-2">Toggle Classes:</span>
            {data?.classes.map((c) => {
              const active = activeClasses[c.classification] !== false;
              const color = CLASS_COLORS[c.classification] || {
                stroke: "#94A3B8",
                fill: "",
              };
              return (
                <button
                  key={c.classification}
                  onClick={() => toggleClass(c.classification)}
                  className={`px-3 py-1 rounded-lg text-xs font-mono border transition-all flex items-center gap-2 ${
                    active
                      ? "bg-slate-800 text-slate-100 border-slate-700 shadow-sm"
                      : "bg-slate-950/50 text-slate-500 border-slate-800/80 opacity-60"
                  }`}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: color.stroke }}
                  />
                  <span>{c.classification.replace(/_/g, " ")}</span>
                  <span className="text-[10px] text-slate-400 font-bold">
                    {c.expansion_rate_sq_m_per_day} m²/d
                  </span>
                </button>
              );
            })}
          </div>

          {/* Chart Canvas Container */}
          <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 h-[340px] relative">
            <canvas ref={canvasRef} />
          </div>
        </div>
      </div>
    </div>
  );
};
