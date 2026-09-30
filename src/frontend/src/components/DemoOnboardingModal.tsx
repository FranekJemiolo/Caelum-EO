import React, { useState } from "react";
import {
  Satellite,
  Shield,
  Layers,
  Network,
  Mountain,
  Radio,
  Sliders,
  CheckCircle,
  ExternalLink,
  X,
  Sparkles,
} from "lucide-react";

interface DemoOnboardingModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DemoOnboardingModal: React.FC<DemoOnboardingModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [dontShowAgain, setDontShowAgain] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleDismiss = () => {
    if (dontShowAgain) {
      try {
        localStorage.setItem("caelum_hide_demo_onboarding", "true");
      } catch {
        // ignore
      }
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in font-sans">
      <div className="relative w-full max-w-2xl bg-slate-950 border border-cyan-500/40 rounded-2xl shadow-[0_0_50px_rgba(0,242,254,0.15)] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Top Glowing Accent Line */}
        <div className="h-1 w-full bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-600" />

        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Satellite size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-100 font-mono tracking-wide">
                  PROJECT CAELUM-EO
                </h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-400/20 text-cyan-300 border border-cyan-500/30">
                  DEMO SHOWCASE
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Autonomous Space-to-Surface GEOINT Intelligence Console
              </p>
            </div>
          </div>
          <button
            onClick={handleDismiss}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-sm text-slate-300 leading-relaxed font-sans">
          {/* Mission Overview Box */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-cyan-400 font-mono text-xs font-bold uppercase tracking-wider">
              <Shield size={14} />
              <span>Air-Gapped Architecture · In-Browser Simulation</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              You are viewing a static demonstration of the{" "}
              <strong className="text-slate-100">Caelum-EO</strong> tactical
              intelligence system. In real-world deployments, Caelum-EO operates
              within a 100% air-gapped, bare-metal server cluster ingesting
              multi-spectral Sentinel-2 and Sentinel-1 SAR satellite passes,
              executing IBM Prithvi / YOLO foundation models, and pushing
              Cursor-on-Target telemetry to front-line troops via ATAK.
            </p>
            <p className="text-xs text-slate-400">
              This interactive GitHub Pages build runs entirely client-side
              using frozen high-fidelity GEOINT snapshots from the{" "}
              <strong className="text-slate-200">
                Suwalki Strategic Corridor
              </strong>{" "}
              scenario.
            </p>
          </div>

          {/* Interactive Feature Guide */}
          <div>
            <h3 className="text-xs font-mono font-bold text-slate-200 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Sparkles size={14} className="text-cyan-400" />
              Interactive Capabilities to Explore
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Feature 1 */}
              <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80 flex items-start gap-3">
                <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 shrink-0 mt-0.5">
                  <Layers size={16} />
                </div>
                <div>
                  <div className="font-mono text-xs font-bold text-slate-100">
                    Multi-Temporal Swipe
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Click any detection polygon (e.g. Radar Dome or Airfield) to
                    swipe between baseline T0 and monitoring T1 imagery.
                  </div>
                </div>
              </div>

              {/* Feature 2 */}
              <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80 flex items-start gap-3">
                <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400 shrink-0 mt-0.5">
                  <Network size={16} />
                </div>
                <div>
                  <div className="font-mono text-xs font-bold text-slate-100">
                    Strategic RL Network
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Open the{" "}
                    <strong className="text-purple-300">Network</strong> tool to
                    inspect supply chain bottlenecks and PPO agent build-out
                    forecasts.
                  </div>
                </div>
              </div>

              {/* Feature 3 */}
              <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80 flex items-start gap-3">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 shrink-0 mt-0.5">
                  <Mountain size={16} />
                </div>
                <div>
                  <div className="font-mono text-xs font-bold text-slate-100">
                    3D Terrain & Viewshed
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Toggle{" "}
                    <strong className="text-emerald-300">3D Terrain</strong> and
                    click radar sites to calculate Line-of-Sight radar masking
                    coverage.
                  </div>
                </div>
              </div>

              {/* Feature 4 */}
              <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80 flex items-start gap-3">
                <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 shrink-0 mt-0.5">
                  <Radio size={16} />
                </div>
                <div>
                  <div className="font-mono text-xs font-bold text-slate-100">
                    ATAK / CoT Dispatch
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Select a target and test dispatching real-time
                    Cursor-on-Target military markers to tactical edge networks.
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Tips */}
          <div className="px-3.5 py-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-300 text-xs font-mono flex items-center gap-2">
            <Sliders size={14} className="shrink-0 text-blue-400" />
            <span>
              Tip: Try approving or rejecting detections — your reviews update
              locally in real-time!
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/70 flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs font-mono text-slate-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
              className="rounded border-slate-700 bg-slate-950 text-cyan-500 focus:ring-cyan-500/40"
            />
            <span>Don&apos;t show on next visit</span>
          </label>
          <div className="flex items-center gap-3">
            <a
              href="https://github.com/FranekJemiolo/Caelum-EO"
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-2 rounded-xl border border-slate-700 hover:border-slate-600 text-slate-300 hover:text-slate-100 font-mono text-xs flex items-center gap-1.5 transition-colors"
            >
              <span>GitHub</span>
              <ExternalLink size={12} />
            </a>
            <button
              onClick={handleDismiss}
              className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-mono font-bold text-xs tracking-wider uppercase transition-all shadow-[0_0_20px_rgba(0,242,254,0.3)] flex items-center gap-2 cursor-pointer"
            >
              <span>Launch Intelligence Console</span>
              <CheckCircle size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
