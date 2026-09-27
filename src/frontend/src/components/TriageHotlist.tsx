import React from 'react';
import { AlertTriangle, ChevronRight, Eye, CheckCircle2, XCircle, ShieldAlert } from 'lucide-react';
import { DetectionFeature } from '../types';

interface TriageHotlistProps {
  items: DetectionFeature[];
  isOpen: boolean;
  onToggle: () => void;
  onSelectTarget: (feature: DetectionFeature) => void;
  onInspect: (feature: DetectionFeature) => void;
  selectedId: string | null;
}

export const TriageHotlist: React.FC<TriageHotlistProps> = ({
  items,
  isOpen,
  onToggle,
  onSelectTarget,
  onInspect,
  selectedId,
}) => {
  // Sort by priority_score descending
  const sortedItems = [...items].sort(
    (a, b) => (b.properties.priority_score || 0) - (a.properties.priority_score || 0)
  );

  return (
    <aside
      className={`fixed top-4 right-4 z-20 flex transition-all duration-300 ${
        isOpen ? 'translate-x-0' : 'translate-x-[calc(100%-48px)]'
      }`}
    >
      {/* Toggle Tab Button */}
      <button
        onClick={onToggle}
        className="h-12 w-12 bg-slate-900/90 text-cyan-400 border border-slate-700/80 rounded-l-xl flex items-center justify-center backdrop-blur-md hover:bg-slate-800 transition-colors shadow-2xl focus:outline-none"
        title={isOpen ? 'Collapse Triage Hotlist' : 'Open Triage Hotlist'}
      >
        {isOpen ? <ChevronRight size={20} /> : <ShieldAlert size={20} className="animate-pulse" />}
      </button>

      {/* Main Drawer Container */}
      <div className="w-80 md:w-96 max-h-[calc(100vh-32px)] bg-slate-950/95 border border-slate-800 backdrop-blur-xl rounded-r-xl rounded-bl-xl shadow-2xl flex flex-col overflow-hidden text-slate-100">
        {/* Header */}
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-400" />
            <h2 className="font-bold text-sm tracking-wider uppercase text-cyan-400 font-mono">
              Priority Triage Hotlist
            </h2>
          </div>
          <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-cyan-950/80 text-cyan-300 border border-cyan-800/60">
            {sortedItems.length} Alerts
          </span>
        </div>

        {/* Scrollable Alerts List */}
        <div className="overflow-y-auto flex-1 p-3 space-y-2.5 divide-y divide-slate-800/40">
          {sortedItems.length === 0 ? (
            <div className="py-12 text-center text-slate-500 text-xs font-mono">
              No pending triage alerts detected.
            </div>
          ) : (
            sortedItems.map((item) => {
              const isSelected = selectedId === item.id;
              const props = item.properties;
              const prio = props.priority_score || 0;

              return (
                <div
                  key={item.id}
                  onClick={() => onSelectTarget(item)}
                  className={`pt-2.5 first:pt-0 p-3 rounded-lg cursor-pointer transition-all border ${
                    isSelected
                      ? 'bg-cyan-950/30 border-cyan-500/50 shadow-[0_0_15px_rgba(0,242,254,0.15)]'
                      : 'bg-slate-900/40 border-slate-800/60 hover:bg-slate-900/80 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="text-xs font-bold text-slate-200 tracking-wide">
                        {props.classification.replace(/_/g, ' ')}
                      </span>
                      <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                        {props.detection_timestamp?.slice(0, 10)} · {props.sensor_source?.slice(0, 11)}
                      </div>
                    </div>

                    {/* Priority Badge */}
                    <div className="flex flex-col items-end gap-1">
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                          prio >= 0.85
                            ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                            : prio >= 0.70
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                            : 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                        }`}
                      >
                        P-{(prio * 100).toFixed(0)}
                      </span>
                    </div>
                  </div>

                  {/* Status & Action Buttons */}
                  <div className="mt-3 flex items-center justify-between text-xs pt-2 border-t border-slate-800/60">
                    <span className="flex items-center gap-1.5 text-[11px] font-mono">
                      {props.review_status === 'VERIFIED' ? (
                        <>
                          <CheckCircle2 size={13} className="text-emerald-400" />
                          <span className="text-emerald-400">VERIFIED</span>
                        </>
                      ) : props.review_status === 'FALSE_POSITIVE' ? (
                        <>
                          <XCircle size={13} className="text-rose-400" />
                          <span className="text-rose-400">FALSE POS</span>
                        </>
                      ) : (
                        <>
                          <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                          <span className="text-amber-400 font-semibold">PENDING</span>
                        </>
                      )}
                    </span>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onInspect(item);
                      }}
                      className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 text-cyan-400 hover:bg-cyan-900/40 hover:text-cyan-300 transition-colors font-mono text-[11px] border border-cyan-900/50"
                    >
                      <Eye size={12} />
                      Inspect
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
};
