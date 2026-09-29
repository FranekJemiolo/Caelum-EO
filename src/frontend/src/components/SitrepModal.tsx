import React, { useState, useEffect } from "react";
import {
  X,
  FileText,
  Sparkles,
  Printer,
  Copy,
  Check,
  Edit3,
  Save,
  Clock,
  ShieldAlert,
  Target,
  RefreshCw,
} from "lucide-react";
import { AuthUser } from "../types";
import { authFetch } from "../auth";

export interface SitrepRecord {
  id: string;
  title: string;
  time_window_start: string;
  time_window_end: string;
  model_name: string;
  sitrep_content: string;
  target_count: number;
  high_priority_count: number;
  status: string;
  created_at: string;
}

interface SitrepModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  apiUrl?: string;
}

export const SitrepModal: React.FC<SitrepModalProps> = ({
  isOpen,
  onClose,
  currentUser,
  apiUrl = "http://localhost:8000",
}) => {
  const [sitreps, setSitreps] = useState<SitrepRecord[]>([]);
  const [selectedSitrep, setSelectedSitrep] = useState<SitrepRecord | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState("");
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadSitreps();
    }
  }, [isOpen]);

  const loadSitreps = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${apiUrl}/api/v1/sitreps?limit=20`);
      if (res.ok) {
        const data: SitrepRecord[] = await res.json();
        setSitreps(data);
        if (data.length > 0 && !selectedSitrep) {
          setSelectedSitrep(data[0]);
          setEditedContent(data[0].sitrep_content);
        }
      }
    } catch (err) {
      console.warn("Failed fetching SITREPs:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateSitrep = async () => {
    setGenerating(true);
    setStatusFeedback(null);
    try {
      const res = await authFetch(`${apiUrl}/api/v1/sitreps/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hours_lookback: 24,
          model: "llama3:8b-instruct",
        }),
      });
      if (res.ok) {
        const newReport: SitrepRecord = await res.json();
        setSitreps([newReport, ...sitreps]);
        setSelectedSitrep(newReport);
        setEditedContent(newReport.sitrep_content);
        setIsEditing(false);
        setStatusFeedback(
          "New military SITREP generated successfully via local AI engine!",
        );
      }
    } catch (err: any) {
      setStatusFeedback(
        `Generation error: ${err.message || "Failed calling local LLM"}`,
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!selectedSitrep) return;
    setSaving(true);
    try {
      const res = await authFetch(
        `${apiUrl}/api/v1/sitreps/${selectedSitrep.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sitrep_content: editedContent,
            title: selectedSitrep.title,
          }),
        },
      );
      if (res.ok) {
        const updated: SitrepRecord = await res.json();
        setSelectedSitrep(updated);
        setSitreps(sitreps.map((s) => (s.id === updated.id ? updated : s)));
        setIsEditing(false);
        setStatusFeedback("SITREP edits persisted successfully!");
      }
    } catch (err: any) {
      setStatusFeedback(`Save error: ${err.message || "Failed saving edits"}`);
    } finally {
      setSaving(false);
    }
  };

  const handleCopyClipboard = () => {
    if (!selectedSitrep) return;
    navigator.clipboard.writeText(
      isEditing ? editedContent : selectedSitrep.sitrep_content,
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => {
    window.print();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-6xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/20 text-cyan-400 border border-cyan-500/40">
              <FileText size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-100 font-mono tracking-wide">
                  AUTOMATED MILITARY SITUATION REPORTS (SITREPs)
                </h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  LOCAL OLLAMA LLM // AIR-GAPPED
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Automated multi-temporal intelligence synthesis • Zero external
                network transmission
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

        {/* Status Notification Banner */}
        {statusFeedback && (
          <div className="px-6 py-2 bg-cyan-950/80 border-b border-cyan-800/60 text-cyan-300 text-xs font-mono flex items-center justify-between">
            <span>{statusFeedback}</span>
            <button
              onClick={() => setStatusFeedback(null)}
              className="text-cyan-400 hover:text-white"
            >
              <X size={13} />
            </button>
          </div>
        )}

        {/* Content Body: Sidebar list + Report Reader/Editor */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left Column: Report History Ledger */}
          <aside className="w-80 border-r border-slate-800 bg-slate-950/50 flex flex-col">
            <div className="p-3 border-b border-slate-800 flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-slate-300">
                SITREP ARCHIVE
              </span>
              <button
                onClick={handleGenerateSitrep}
                disabled={generating}
                className="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-slate-950 text-xs font-mono font-bold flex items-center gap-1.5 transition-colors disabled:opacity-50"
              >
                <Sparkles size={13} />
                {generating ? "Drafting..." : "Generate SITREP"}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-2">
              {loading && sitreps.length === 0 ? (
                <div className="p-4 text-center text-xs font-mono text-slate-500 flex items-center justify-center gap-2">
                  <RefreshCw size={14} className="animate-spin" />
                  Loading SITREP ledger...
                </div>
              ) : sitreps.length === 0 ? (
                <div className="p-6 text-center text-xs font-mono text-slate-500">
                  No SITREPs generated yet. Click "Generate SITREP" to draft a
                  report.
                </div>
              ) : (
                sitreps.map((report) => (
                  <div
                    key={report.id}
                    onClick={() => {
                      setSelectedSitrep(report);
                      setEditedContent(report.sitrep_content);
                      setIsEditing(false);
                    }}
                    className={`p-3 rounded-xl border text-xs font-mono cursor-pointer transition-all ${
                      selectedSitrep?.id === report.id
                        ? "bg-slate-900 border-cyan-500/60 shadow-lg text-slate-100"
                        : "bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                    }`}
                  >
                    <div className="font-bold text-slate-200 truncate mb-1">
                      {report.title}
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span className="flex items-center gap-1">
                        <Clock size={11} />
                        {report.created_at.slice(0, 16).replace("T", " ")}Z
                      </span>
                      <span className="flex items-center gap-1 text-amber-400 font-bold">
                        <Target size={11} />
                        {report.target_count} tgts
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-1 text-[10px]">
                      <span className="px-1.5 py-0.2 rounded bg-slate-800 text-cyan-300">
                        {report.model_name}
                      </span>
                      {report.high_priority_count > 0 && (
                        <span className="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 flex items-center gap-1">
                          <ShieldAlert size={10} />
                          {report.high_priority_count} critical
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </aside>

          {/* Right Column: Full Report Inspection & Action Toolbar */}
          <main className="flex-1 flex flex-col bg-slate-900 overflow-hidden">
            {selectedSitrep ? (
              <>
                {/* Action Toolbar */}
                <div className="px-6 py-3 border-b border-slate-800 bg-slate-950/40 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-slate-400">
                      Status:{" "}
                      <b className="text-emerald-400">
                        {selectedSitrep.status}
                      </b>
                    </span>
                    <span className="text-xs font-mono text-slate-600">|</span>
                    <span className="text-xs font-mono text-slate-400">
                      Model: <b>{selectedSitrep.model_name}</b>
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {isEditing ? (
                      <button
                        onClick={handleSaveEdit}
                        disabled={saving}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-mono text-xs font-bold rounded-lg flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      >
                        <Save size={13} />
                        {saving ? "Saving..." : "Save Edits"}
                      </button>
                    ) : (
                      <button
                        onClick={() => setIsEditing(true)}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-mono text-xs font-bold rounded-lg border border-slate-700 flex items-center gap-1.5 transition-colors"
                      >
                        <Edit3 size={13} className="text-cyan-400" />
                        Edit Text
                      </button>
                    )}

                    <button
                      onClick={handleCopyClipboard}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-mono text-xs rounded-lg border border-slate-700 flex items-center gap-1.5 transition-colors"
                    >
                      {copied ? (
                        <Check size={13} className="text-emerald-400" />
                      ) : (
                        <Copy size={13} />
                      )}
                      {copied ? "Copied" : "Copy"}
                    </button>

                    <button
                      onClick={handlePrint}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-mono text-xs rounded-lg border border-slate-700 flex items-center gap-1.5 transition-colors"
                    >
                      <Printer size={13} className="text-cyan-400" />
                      Print / PDF
                    </button>
                  </div>
                </div>

                {/* Report Content Body */}
                <div className="flex-1 overflow-y-auto p-8">
                  {isEditing ? (
                    <textarea
                      value={editedContent}
                      onChange={(e) => setEditedContent(e.target.value)}
                      className="w-full h-full p-4 bg-slate-950 border border-slate-700 rounded-xl font-mono text-xs text-slate-200 leading-relaxed focus:outline-none focus:border-cyan-400 resize-none"
                    />
                  ) : (
                    <div className="max-w-4xl mx-auto space-y-4 font-mono text-slate-200 text-xs leading-relaxed whitespace-pre-wrap selection:bg-cyan-500 selection:text-slate-950">
                      {selectedSitrep.sitrep_content}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-500 font-mono text-xs">
                <FileText size={48} className="text-slate-700 mb-3" />
                Select a report from the archive or click "Generate SITREP" to
                create an automated brief.
              </div>
            )}
          </main>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between text-xs font-mono text-slate-500">
          <div>
            Active Operator:{" "}
            <b className="text-slate-300">
              {currentUser?.username || "analyst"}
            </b>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors"
          >
            Close Dashboard
          </button>
        </div>
      </div>
    </div>
  );
};
