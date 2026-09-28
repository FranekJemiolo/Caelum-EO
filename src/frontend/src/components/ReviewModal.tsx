import React, { useState, useEffect } from "react";
import {
  Check,
  Edit3,
  XCircle,
  ArrowRight,
  ShieldCheck,
  Tag,
  X,
  MessageSquare,
} from "lucide-react";
import {
  AuthUser,
  DetectionFeature,
  InfrastructureClass,
  ReviewPayload,
  ReviewStatus,
} from "../types";
import { CommentThread } from "./CommentThread";

interface ReviewModalProps {
  feature: DetectionFeature | null;
  onClose: () => void;
  onSubmitReview: (
    detectionId: string,
    payload: ReviewPayload,
  ) => Promise<void>;
  onNextQueueItem?: () => void;
  currentUser?: AuthUser | null;
  apiUrl?: string;
}

const CLASSIFICATION_OPTIONS: InfrastructureClass[] = [
  "RUNWAY_TAXIWAY",
  "RADAR_DOME",
  "LOGISTICS_DEPOT",
  "DEFENSE_REVETMENT",
  "INDUSTRIAL_BUILDING",
  "UNKNOWN_STRUCTURE",
];

export const ReviewModal: React.FC<ReviewModalProps> = ({
  feature,
  onClose,
  onSubmitReview,
  onNextQueueItem,
  currentUser,
  apiUrl = "http://localhost:8000",
}) => {
  const [activeTab, setActiveTab] = useState<"action" | "notes">("action");
  const [selectedClass, setSelectedClass] = useState<InfrastructureClass>(
    feature?.properties.classification || "UNKNOWN_STRUCTURE",
  );
  const [notes, setNotes] = useState<string>("");
  const analystId = currentUser?.username || "analyst_viper";
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  useEffect(() => {
    if (feature) {
      setSelectedClass(feature.properties.classification);
      setNotes(feature.properties.reviewer_notes || "");
    }
  }, [feature]);

  // Keyboard shortcut listeners: V (Verify), F (False Positive), Space (Next)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Do not trigger if typing in notes input
      if (
        document.activeElement?.tagName === "TEXTAREA" ||
        document.activeElement?.tagName === "INPUT"
      ) {
        return;
      }

      if (e.key === "v" || e.key === "V") {
        handleAction("VERIFIED");
      } else if (e.key === "f" || e.key === "F") {
        handleAction("FALSE_POSITIVE");
      } else if (e.code === "Space" && onNextQueueItem) {
        e.preventDefault();
        onNextQueueItem();
      } else if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  if (!feature) return null;

  const props = feature.properties;

  const handleAction = async (
    status: ReviewStatus,
    overrideClass?: InfrastructureClass,
  ) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const payload: ReviewPayload = {
        review_status: status,
        verified_class:
          status === "FALSE_POSITIVE" ? null : overrideClass || selectedClass,
        reviewer_notes: notes.trim() || undefined,
        reviewed_by: analystId.trim() || "analyst_callsign",
      };
      await onSubmitReview(feature.id, payload);
      if (onNextQueueItem) {
        onNextQueueItem();
      } else {
        onClose();
      }
    } catch (err) {
      console.error("Failed to submit review:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="relative w-full max-w-xl bg-slate-950 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-slate-100">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <ShieldCheck size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100 font-mono tracking-wide">
                HITL TRIAGE & RECLASSIFICATION
              </h2>
              <div className="text-xs text-slate-400 font-mono">
                TARGET ID: {feature.id}
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 bg-slate-900/40 font-mono text-xs">
          <button
            onClick={() => setActiveTab("action")}
            className={`flex-1 py-2.5 px-4 flex items-center justify-center gap-2 border-b-2 font-bold transition-colors ${
              activeTab === "action"
                ? "border-cyan-400 text-cyan-400 bg-cyan-950/20"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <ShieldCheck size={14} />
            <span>Triage & Reclassify</span>
          </button>
          <button
            onClick={() => setActiveTab("notes")}
            className={`flex-1 py-2.5 px-4 flex items-center justify-center gap-2 border-b-2 font-bold transition-colors ${
              activeTab === "notes"
                ? "border-cyan-400 text-cyan-400 bg-cyan-950/20"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <MessageSquare size={14} />
            <span>Analyst Notes Thread</span>
          </button>
        </div>

        {/* Content Body */}
        {activeTab === "notes" ? (
          <div className="p-5">
            <CommentThread
              detectionId={feature.id}
              currentUser={currentUser || null}
              apiUrl={apiUrl}
            />
          </div>
        ) : (
          <div className="p-6 space-y-5">
            {/* Target Metadata Overview */}
            <div className="grid grid-cols-2 gap-3 p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs font-mono">
              <div>
                <span className="text-slate-500 uppercase text-[10px]">
                  Predicted Class:
                </span>
                <div className="font-bold text-cyan-400 mt-0.5">
                  {props.classification.replace(/_/g, " ")}
                </div>
              </div>
              <div>
                <span className="text-slate-500 uppercase text-[10px]">
                  Model Confidence:
                </span>
                <div className="font-bold text-slate-200 mt-0.5">
                  {(props.confidence * 100).toFixed(1)}%
                </div>
              </div>
              <div>
                <span className="text-slate-500 uppercase text-[10px]">
                  Geodesic Footprint:
                </span>
                <div className="font-bold text-slate-300 mt-0.5">
                  {props.area_sq_meters
                    ? `${Math.round(props.area_sq_meters).toLocaleString()} m²`
                    : "N/A"}
                </div>
              </div>
              <div>
                <span className="text-slate-500 uppercase text-[10px]">
                  Current Review:
                </span>
                <div className="font-bold text-amber-400 mt-0.5">
                  {props.review_status}
                </div>
              </div>
            </div>

            {/* Reclassification Selector */}
            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1.5 flex items-center gap-1.5">
                <Tag size={13} className="text-cyan-400" />
                Verified Infrastructure Classification
              </label>
              <select
                value={selectedClass}
                onChange={(e) =>
                  setSelectedClass(e.target.value as InfrastructureClass)
                }
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-slate-100 text-sm font-mono focus:border-cyan-400 focus:outline-none transition-colors"
              >
                {CLASSIFICATION_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>

            {/* Analyst Notes Input */}
            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1.5 flex items-center gap-1.5">
                <Edit3 size={13} className="text-amber-400" />
                Intelligence Notes & Analyst Assessment
              </label>
              <textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Concrete apron identified with perimeter security fencing..."
                className="w-full px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-700/80 text-slate-100 text-xs font-mono focus:border-cyan-400 focus:outline-none transition-colors resize-none placeholder:text-slate-600"
              />
            </div>

            {/* Action Buttons */}
            <div className="grid grid-cols-3 gap-2.5 pt-2">
              {/* [V] Verify Correct */}
              <button
                disabled={isSubmitting}
                onClick={() => handleAction("VERIFIED", props.classification)}
                className="flex flex-col items-center justify-center p-3 rounded-xl bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-600/30 transition-all font-mono group"
              >
                <Check
                  size={18}
                  className="mb-1 text-emerald-400 group-hover:scale-110 transition-transform"
                />
                <span className="text-xs font-bold">[V] Verify</span>
                <span className="text-[9px] text-emerald-400/80">
                  Confirmed
                </span>
              </button>

              {/* [M] Reclassify */}
              <button
                disabled={isSubmitting}
                onClick={() => handleAction("MISCLASSIFIED", selectedClass)}
                className="flex flex-col items-center justify-center p-3 rounded-xl bg-cyan-600/20 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-600/30 transition-all font-mono group"
              >
                <Edit3
                  size={18}
                  className="mb-1 text-cyan-400 group-hover:scale-110 transition-transform"
                />
                <span className="text-xs font-bold">[M] Reclassify</span>
                <span className="text-[9px] text-cyan-400/80">New Label</span>
              </button>

              {/* [F] Mark False Positive */}
              <button
                disabled={isSubmitting}
                onClick={() => handleAction("FALSE_POSITIVE")}
                className="flex flex-col items-center justify-center p-3 rounded-xl bg-rose-600/20 border border-rose-500/40 text-rose-300 hover:bg-rose-600/30 transition-all font-mono group"
              >
                <XCircle
                  size={18}
                  className="mb-1 text-rose-400 group-hover:scale-110 transition-transform"
                />
                <span className="text-xs font-bold">[F] False Pos</span>
                <span className="text-[9px] text-rose-400/80">
                  Reject Anomaly
                </span>
              </button>
            </div>

            {/* Quick Shortcuts Hint */}
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 pt-2 border-t border-slate-800">
              <span>Keys: [V] Verify · [F] False Pos · [Esc] Close</span>
              {onNextQueueItem && (
                <span
                  className="text-cyan-400 flex items-center gap-1 cursor-pointer"
                  onClick={onNextQueueItem}
                >
                  Next Target [Space] <ArrowRight size={12} />
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
