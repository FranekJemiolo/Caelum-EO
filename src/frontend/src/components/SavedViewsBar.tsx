import React, { useState, useEffect, useCallback } from "react";
import { Bookmark, Plus, X, Check, Filter } from "lucide-react";
import { SavedFilter } from "../types";
import { authFetch } from "../auth";

interface SavedViewsBarProps {
  currentFilters: {
    classification?: string;
    minConfidence?: number;
    zoneId?: string;
    reviewStatus?: string;
  };
  onApplyFilter: (filters: {
    classification?: string;
    minConfidence?: number;
    zoneId?: string;
    reviewStatus?: string;
  }) => void;
  apiUrl?: string;
}

export const SavedViewsBar: React.FC<SavedViewsBarProps> = ({
  currentFilters,
  onApplyFilter,
  apiUrl = "http://localhost:8000",
}) => {
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [newViewName, setNewViewName] = useState("");
  const [activeFilterId, setActiveFilterId] = useState<string | null>(null);

  const fetchSavedFilters = useCallback(async () => {
    try {
      const res = await authFetch(`${apiUrl}/api/v1/saved-filters`);
      if (res.ok) {
        const data = await res.json();
        setSavedFilters(data);
      }
    } catch {
      // Fallback in memory
      setSavedFilters([
        {
          id: "seed-1",
          user_id: "u1",
          name: "High-Confidence Radars",
          filter_json: {
            classification: "RADAR_DOME",
            minConfidence: 0.85,
          },
          created_at: new Date().toISOString(),
        },
        {
          id: "seed-2",
          user_id: "u1",
          name: "Pending Runways",
          filter_json: {
            classification: "RUNWAY_TAXIWAY",
            reviewStatus: "PENDING_REVIEW",
          },
          created_at: new Date().toISOString(),
        },
      ]);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchSavedFilters();
  }, [fetchSavedFilters]);

  const handleSaveCurrentView = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newViewName.trim()) return;

    try {
      const payload = {
        name: newViewName.trim(),
        filter_json: currentFilters,
      };
      const res = await authFetch(`${apiUrl}/api/v1/saved-filters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const created: SavedFilter = await res.json();
        setSavedFilters((prev) => [created, ...prev]);
        setActiveFilterId(created.id);
        setNewViewName("");
        setIsAdding(false);
      }
    } catch {
      const mockSaved: SavedFilter = {
        id: `mock-${Date.now()}`,
        user_id: "u1",
        name: newViewName.trim(),
        filter_json: currentFilters,
        created_at: new Date().toISOString(),
      };
      setSavedFilters((prev) => [mockSaved, ...prev]);
      setActiveFilterId(mockSaved.id);
      setNewViewName("");
      setIsAdding(false);
    }
  };

  const handleDeleteFilter = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await authFetch(`${apiUrl}/api/v1/saved-filters/${id}`, { method: "DELETE" });
    } catch {
      // Ignore
    }
    setSavedFilters((prev) => prev.filter((f) => f.id !== id));
    if (activeFilterId === id) {
      setActiveFilterId(null);
    }
  };

  const handleSelectFilter = (filter: SavedFilter) => {
    if (activeFilterId === filter.id) {
      setActiveFilterId(null);
      // Reset filter
      onApplyFilter({});
    } else {
      setActiveFilterId(filter.id);
      onApplyFilter(filter.filter_json);
    }
  };

  return (
    <div className="absolute top-4 left-4 z-20 flex flex-wrap items-center gap-2 max-w-[calc(100vw-420px)] font-mono text-xs">
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-950/90 border border-slate-800 backdrop-blur-md text-slate-300 shadow-xl">
        <Bookmark size={13} className="text-cyan-400" />
        <span className="text-[11px] font-bold uppercase tracking-wider text-cyan-400">
          Saved Views
        </span>
      </div>

      {/* Chips */}
      {savedFilters.map((filter) => {
        const isActive = activeFilterId === filter.id;
        return (
          <button
            key={filter.id}
            onClick={() => handleSelectFilter(filter)}
            className={`group flex items-center gap-2 px-3 py-1.5 rounded-lg border backdrop-blur-md transition-all shadow-lg text-[11px] font-semibold ${
              isActive
                ? "bg-cyan-950/80 border-cyan-400 text-cyan-200 shadow-[0_0_12px_rgba(0,242,254,0.25)]"
                : "bg-slate-950/80 border-slate-800 text-slate-300 hover:border-slate-700 hover:text-white"
            }`}
          >
            <Filter size={11} className={isActive ? "text-cyan-400" : "text-slate-500"} />
            <span>{filter.name}</span>
            <span
              onClick={(e) => handleDeleteFilter(filter.id, e)}
              className="p-0.5 rounded hover:bg-slate-800 hover:text-rose-400 transition-colors text-slate-500 opacity-0 group-hover:opacity-100"
              title="Delete preset"
            >
              <X size={11} />
            </span>
          </button>
        );
      })}

      {/* Add View Button or Input Form */}
      {isAdding ? (
        <form
          onSubmit={handleSaveCurrentView}
          className="flex items-center gap-1.5 bg-slate-950/90 border border-cyan-500/80 rounded-lg p-1 backdrop-blur-md shadow-xl"
        >
          <input
            type="text"
            autoFocus
            value={newViewName}
            onChange={(e) => setNewViewName(e.target.value)}
            placeholder="View name (e.g. Radars 90%)..."
            className="px-2 py-1 bg-transparent text-slate-200 text-xs focus:outline-none placeholder:text-slate-600 font-sans w-44"
          />
          <button
            type="submit"
            className="p-1 rounded bg-cyan-600 hover:bg-cyan-500 text-slate-950 transition-colors"
            title="Confirm Save"
          >
            <Check size={12} />
          </button>
          <button
            type="button"
            onClick={() => setIsAdding(false)}
            className="p-1 rounded hover:bg-slate-800 text-slate-400 transition-colors"
            title="Cancel"
          >
            <X size={12} />
          </button>
        </form>
      ) : (
        <button
          onClick={() => setIsAdding(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-950/70 border border-dashed border-slate-700/80 hover:border-cyan-400 hover:text-cyan-300 text-slate-400 backdrop-blur-md transition-all text-[11px]"
          title="Save current filters as quick-access view"
        >
          <Plus size={12} />
          <span>Save Current View</span>
        </button>
      )}
    </div>
  );
};
