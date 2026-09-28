import React, { useState, useEffect, useCallback } from "react";
import { History, Shield, CheckCircle2, XCircle, AlertCircle, Clock, User, Loader2 } from "lucide-react";
import { DetectionAuditRecord } from "../types";
import { authFetch } from "../auth";

interface AuditTimelineProps {
  detectionId: string;
  apiUrl?: string;
}

export const AuditTimeline: React.FC<AuditTimelineProps> = ({
  detectionId,
  apiUrl = "http://localhost:8000",
}) => {
  const [auditLogs, setAuditLogs] = useState<DetectionAuditRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchAuditLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await authFetch(`${apiUrl}/api/v1/detections/${detectionId}/audit`);
      if (res.ok) {
        const data = await res.json();
        setAuditLogs(data);
      } else {
        setAuditLogs([]);
      }
    } catch {
      setAuditLogs([]);
    } finally {
      setIsLoading(false);
    }
  }, [apiUrl, detectionId]);

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "VERIFIED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 size={11} /> VERIFIED
          </span>
        );
      case "FALSE_POSITIVE":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
            <XCircle size={11} /> FALSE POSITIVE
          </span>
        );
      case "MISCLASSIFIED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
            <AlertCircle size={11} /> MISCLASSIFIED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">
            <Clock size={11} /> {status || "PENDING"}
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden font-mono text-xs">
      {/* Header */}
      <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2 text-cyan-400">
          <History size={16} />
          <h3 className="font-bold uppercase tracking-wider text-xs">
            Operational Audit Trail & Lifecycle
          </h3>
        </div>
        <span className="text-[10px] text-slate-500 px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
          Target: {detectionId.slice(0, 8)}...
        </span>
      </div>

      {/* Timeline container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {isLoading ? (
          <div className="flex items-center justify-center h-40 text-slate-500 gap-2">
            <Loader2 size={16} className="animate-spin text-cyan-400" />
            <span>Retrieving cryptographically logged lifecycle records...</span>
          </div>
        ) : auditLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-slate-500 text-center">
            <Shield size={28} className="mb-2 opacity-30 text-cyan-400" />
            <span>No previous lifecycle state transitions recorded.</span>
            <span className="text-[10px] text-slate-600 mt-1">
              Target remains in initial automated model detection state.
            </span>
          </div>
        ) : (
          <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-700/60">
            {auditLogs.map((log) => (
              <div key={log.id} className="relative group">
                {/* Timeline node icon */}
                <div className="absolute -left-6 top-1 w-3 h-3 rounded-full bg-cyan-400 border-2 border-slate-950 shadow-[0_0_8px_rgba(0,242,254,0.6)]" />

                <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800/90 hover:border-slate-700 transition-colors shadow-lg space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      {log.previous_state && (
                        <>
                          {getStatusBadge(log.previous_state)}
                          <span className="text-slate-500">→</span>
                        </>
                      )}
                      {getStatusBadge(log.new_state)}
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                      <Clock size={11} className="text-slate-500" />
                      <span>{log.timestamp ? new Date(log.timestamp).toLocaleString() : "N/A"}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 text-[11px] text-slate-400 pt-1">
                    <User size={12} className="text-cyan-400" />
                    <span>Action by:</span>
                    <span className="text-cyan-300 font-semibold">{log.username || "System Operator"}</span>
                  </div>

                  {log.note && (
                    <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800/60 text-slate-300 font-sans text-xs">
                      {log.note}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
