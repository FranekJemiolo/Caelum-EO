import React, { useState, useEffect, useCallback } from "react";
import { MessageSquare, Send, User, Clock, Loader2 } from "lucide-react";
import { AuthUser, DetectionComment } from "../types";
import { authFetch } from "../auth";

interface CommentThreadProps {
  detectionId: string;
  currentUser: AuthUser | null;
  apiUrl?: string;
}

export const CommentThread: React.FC<CommentThreadProps> = ({
  detectionId,
  currentUser,
  apiUrl = "http://localhost:8000",
}) => {
  const [comments, setComments] = useState<DetectionComment[]>([]);
  const [newComment, setNewComment] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchComments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authFetch(
        `${apiUrl}/api/v1/detections/${detectionId}/comments`,
      );
      if (res.ok) {
        const data = await res.json();
        setComments(data);
      } else {
        // Fallback for offline demo
        setComments([]);
      }
    } catch {
      setComments([]);
    } finally {
      setIsLoading(false);
    }
  }, [apiUrl, detectionId]);

  useEffect(() => {
    fetchComments();
  }, [fetchComments]);

  const handleSendComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim() || isSending) return;

    setIsSending(true);
    setError(null);
    try {
      const res = await authFetch(
        `${apiUrl}/api/v1/detections/${detectionId}/comments`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ comment: newComment.trim() }),
        },
      );
      if (res.ok) {
        const created: DetectionComment = await res.json();
        setComments((prev) => [...prev, created]);
        setNewComment("");
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || "Failed to submit comment");
      }
    } catch {
      // In offline fallback mode, add locally
      const localEntry: DetectionComment = {
        id: `local-${Date.now()}`,
        detection_id: detectionId,
        username: currentUser?.username || "analyst_viper",
        comment: newComment.trim(),
        created_at: new Date().toISOString(),
      };
      setComments((prev) => [...prev, localEntry]);
      setNewComment("");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden font-mono text-xs">
      {/* Header */}
      <div className="px-4 py-2.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2 text-cyan-400">
          <MessageSquare size={14} />
          <span className="font-bold tracking-wider uppercase text-[11px]">
            Analyst Collaboration Thread ({comments.length})
          </span>
        </div>
        <span className="text-[10px] text-slate-500">Air-Gapped Local Log</span>
      </div>

      {/* Messages list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-[140px] max-h-[220px]">
        {isLoading ? (
          <div className="flex items-center justify-center h-28 text-slate-500 gap-2">
            <Loader2 size={16} className="animate-spin text-cyan-400" />
            <span>Loading intelligence thread...</span>
          </div>
        ) : comments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-28 text-slate-500 text-center px-4">
            <MessageSquare
              size={24}
              className="mb-1 opacity-30 text-cyan-400"
            />
            <span>No analyst notes recorded yet.</span>
            <span className="text-[10px] text-slate-600 mt-0.5">
              Leave observations for shift handover.
            </span>
          </div>
        ) : (
          comments.map((c) => (
            <div
              key={c.id}
              className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 space-y-1.5"
            >
              <div className="flex items-center justify-between text-[10px]">
                <div className="flex items-center gap-1.5 text-cyan-300 font-semibold">
                  <User size={11} className="text-cyan-400" />
                  <span>{c.username}</span>
                </div>
                <div className="flex items-center gap-1 text-slate-500 text-[9px]">
                  <Clock size={10} />
                  <span>
                    {c.created_at
                      ? new Date(c.created_at).toLocaleString()
                      : "Just now"}
                  </span>
                </div>
              </div>
              <p className="text-slate-300 leading-relaxed break-words font-sans text-xs">
                {c.comment}
              </p>
            </div>
          ))
        )}
      </div>

      {/* Input box */}
      <form
        onSubmit={handleSendComment}
        className="p-2.5 bg-slate-950 border-t border-slate-800 flex gap-2"
      >
        <input
          type="text"
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add operational note or verification context..."
          className="flex-1 bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-1.5 text-slate-200 text-xs placeholder:text-slate-600 focus:outline-none focus:border-cyan-400 font-sans"
        />
        <button
          type="submit"
          disabled={!newComment.trim() || isSending}
          className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:hover:bg-cyan-600 text-slate-950 font-bold transition-colors flex items-center gap-1 text-[11px]"
        >
          {isSending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Send size={13} />
          )}
          <span>Post</span>
        </button>
      </form>
      {error && (
        <div className="px-3 py-1 bg-rose-950/80 text-rose-300 text-[10px]">
          {error}
        </div>
      )}
    </div>
  );
};
