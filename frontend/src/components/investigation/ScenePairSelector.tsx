import React, { useEffect, useState } from "react";
import { fetchSeriesPairs } from "../../services/api";
import { transformScenePair } from "../../services/transformers";
import type { ScenePair } from "../../types/api";
import type { ScenePairSummary } from "../../types/models";

interface ScenePairSelectorProps {
  seriesId: string;
  selectedPairId: string | null;
  onSelectPair: (pair: ScenePair, summary: ScenePairSummary) => void;
}

export const ScenePairSelector: React.FC<ScenePairSelectorProps> = ({
  seriesId,
  selectedPairId,
  onSelectPair,
}) => {
  const [mode, setMode] = useState<"baseline" | "adjacent" | "all_pairwise">("baseline");
  const [pairs, setPairs] = useState<{ raw: ScenePair; summary: ScenePairSummary }[]>([]);
  const [rejectedPairs, setRejectedPairs] = useState<{ raw: ScenePair; summary: ScenePairSummary }[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const onSelectPairRef = React.useRef(onSelectPair);
  const selectedPairIdRef = React.useRef(selectedPairId);

  useEffect(() => {
    onSelectPairRef.current = onSelectPair;
    selectedPairIdRef.current = selectedPairId;
  });

  const handleModeChange = (newMode: "baseline" | "adjacent" | "all_pairwise") => {
    setMode(newMode);
    setIsLoading(true);
  };

  useEffect(() => {
    let isMounted = true;

    fetchSeriesPairs(seriesId, mode)
      .then((res) => {
        if (!isMounted) return;
        setError(null);
        const validMapped = (res.valid_pairs || []).map((p) => ({
          raw: p,
          summary: transformScenePair(p, seriesId),
        }));
        const rejectedMapped = (res.rejected_pairs || []).map((p) => ({
          raw: p,
          summary: transformScenePair(p, seriesId),
        }));

        setPairs(validMapped);
        setRejectedPairs(rejectedMapped);
        setIsLoading(false);

        // Auto-select first pair if none selected or if previous selection is not in new list
        if (validMapped.length > 0) {
          const currentValid = validMapped.find((p) => p.summary.pairId === selectedPairIdRef.current);
          if (!currentValid) {
            onSelectPairRef.current(validMapped[0].raw, validMapped[0].summary);
          }
        }
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Failed to generate scene pairs for series.");
        setPairs([]);
        setRejectedPairs([]);
        setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [seriesId, mode]);

  return (
    <div className="space-y-4 text-left font-sans">
      {/* Header & Mode Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <span className="w-5 h-5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 flex items-center justify-center font-mono text-[11px] font-bold">
              2
            </span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Select Discovery Scene Pair
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5 ml-7">
            Pairwise temporal combinations evaluated across the series timeline.
          </p>
        </div>

        {/* Mode tabs */}
        <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-xl border border-slate-800 self-start sm:self-auto font-mono text-xs">
          <button
            onClick={() => handleModeChange("baseline")}
            className={`px-3 py-1 rounded-lg transition-all ${
              mode === "baseline"
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Baseline (T0)
          </button>
          <button
            onClick={() => handleModeChange("adjacent")}
            className={`px-3 py-1 rounded-lg transition-all ${
              mode === "adjacent"
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Adjacent
          </button>
          <button
            onClick={() => handleModeChange("all_pairwise")}
            className={`px-3 py-1 rounded-lg transition-all ${
              mode === "all_pairwise"
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            All Pairs
          </button>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="py-8 text-center font-mono text-xs text-slate-400 space-y-2 animate-pulse">
          <div className="w-6 h-6 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <div>Evaluating temporal compatibility & baseline pairs…</div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-xl text-rose-300 text-xs font-mono">
          ⚠️ {error}
        </div>
      )}

      {/* Pairs List */}
      {!isLoading && !error && (
        <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
          {pairs.length === 0 ? (
            <div className="py-8 text-center font-mono text-xs text-slate-400 bg-slate-900/40 rounded-xl border border-slate-800">
              No compatible scene pairs found for this series with mode &apos;{mode}&apos;.
            </div>
          ) : (
            pairs.map(({ raw, summary }) => {
              const isSelected = summary.pairId === selectedPairId;
              return (
                <div
                  key={summary.pairId}
                  onClick={() => onSelectPair(raw, summary)}
                  className={`cursor-pointer rounded-xl p-3.5 border transition-all duration-150 font-mono text-xs ${
                    isSelected
                      ? "bg-slate-900/95 border-cyan-500 shadow-md shadow-cyan-950/40 ring-1 ring-cyan-500/30"
                      : "bg-slate-900/60 hover:bg-slate-900/80 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="flex items-center space-x-2 truncate">
                      <span
                        className={`w-2 h-2 rounded-full flex-shrink-0 ${
                          isSelected ? "bg-cyan-400 animate-pulse" : "bg-slate-600"
                        }`}
                      ></span>
                      <span className="font-bold text-slate-100 truncate" title={summary.pairId}>
                        {summary.pairId}
                      </span>
                    </div>

                    <div className="flex items-center space-x-2">
                      <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                        COMPATIBLE
                      </span>
                      <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-cyan-300 border border-slate-700">
                        {summary.temporalBaselineDays}d separation
                      </span>
                    </div>
                  </div>

                  {/* Epochs Row */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] pt-2 border-t border-slate-800/80">
                    <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
                      <div className="text-[10px] uppercase text-slate-400 font-semibold">
                        Earlier (T1)
                      </div>
                      <div className="text-slate-200 font-medium truncate">
                        {summary.earlierDate} • {summary.earlierPlatform}
                      </div>
                      <div className="text-[10px] text-slate-400 truncate" title={summary.earlierObservationId}>
                        {summary.earlierObservationId}
                      </div>
                    </div>

                    <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
                      <div className="text-[10px] uppercase text-slate-400 font-semibold">
                        Later (T2)
                      </div>
                      <div className="text-slate-200 font-medium truncate">
                        {summary.laterDate} • {summary.laterPlatform}
                      </div>
                      <div className="text-[10px] text-slate-400 truncate" title={summary.laterObservationId}>
                        {summary.laterObservationId}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}

          {/* Rejected pairs if any */}
          {rejectedPairs.length > 0 && (
            <div className="pt-2">
              <div className="text-[11px] font-mono text-slate-400 mb-1.5 font-semibold">
                Incompatible Pairs ({rejectedPairs.length})
              </div>
              <div className="space-y-1.5 opacity-60">
                {rejectedPairs.map(({ summary }) => (
                  <div
                    key={summary.pairId}
                    className="p-2 bg-slate-950 rounded-lg border border-slate-800/80 font-mono text-[11px] flex items-center justify-between"
                  >
                    <span className="truncate text-slate-400">{summary.pairId}</span>
                    <span className="text-amber-400 text-[10px]">
                      {summary.rejectionReasons[0] || "Incompatible"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
