import React, { useEffect, useState } from "react";
import { executeInvestigation, fetchSeriesList } from "../../services/api";
import {
  transformInvestigationDossier,
  transformTemporalSeries,
} from "../../services/transformers";
import type { InvestigationDossier, InvestigationRequest, ScenePair } from "../../types/api";
import type {
  CandidateChange,
  InvestigationSummary,
  ScenePairSummary,
  TemporalSeriesSummary,
} from "../../types/models";
import { CandidateRegionSelector } from "./CandidateRegionSelector";
import { ScenePairSelector } from "./ScenePairSelector";

interface InvestigationLauncherProps {
  seriesList?: TemporalSeriesSummary[];
  selectedSeries?: TemporalSeriesSummary | null;
  initialSeriesId?: string;
  onSelectSeries?: (seriesId: string) => void;
  onInvestigationComplete?: (dossier: InvestigationDossier, summary: InvestigationSummary) => void;
}

export const InvestigationLauncher: React.FC<InvestigationLauncherProps> = ({
  seriesList: propSeriesList,
  selectedSeries: propSelectedSeries,
  initialSeriesId,
  onSelectSeries,
  onInvestigationComplete,
}) => {
  const [internalSeriesList, setInternalSeriesList] = useState<TemporalSeriesSummary[]>(
    propSeriesList || []
  );
  const [internalSeriesId, setInternalSeriesId] = useState<string>(
    propSelectedSeries?.seriesId || initialSeriesId || ""
  );

  const [selectedPairRaw, setSelectedPairRaw] = useState<ScenePair | null>(null);
  const [selectedPairSummary, setSelectedPairSummary] = useState<ScenePairSummary | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateChange | null>(null);
  const [pairingStrategy, setPairingStrategy] = useState<"baseline" | "adjacent">("baseline");

  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [executionStage, setExecutionStage] = useState<string>("Ready");
  const [error, setError] = useState<{
    code: string;
    message: string;
    stage?: string;
  } | null>(null);
  const [lastDossier, setLastDossier] = useState<{
    raw: InvestigationDossier;
    summary: InvestigationSummary;
  } | null>(null);

  // Asynchronous series catalog fetch if not provided via props
  useEffect(() => {
    if (propSeriesList && propSeriesList.length > 0) {
      return;
    }
    let isMounted = true;
    fetchSeriesList()
      .then((raw) => {
        if (!isMounted) return;
        const mapped = raw.map(transformTemporalSeries);
        setInternalSeriesList(mapped);
        setInternalSeriesId((prev) => {
          if (prev) {
            const existing = mapped.find((s) => s.seriesId === prev);
            if (existing && existing.observationCount >= 2) return prev;
          }
          const preferred =
            mapped.find((s) => s.observationCount >= 4) ||
            mapped.find((s) => s.observationCount >= 2) ||
            mapped[0];
          return preferred ? preferred.seriesId : "";
        });
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, [propSeriesList]);

  const seriesList =
    propSeriesList && propSeriesList.length > 0 ? propSeriesList : internalSeriesList;

  const seriesId =
    (internalSeriesId && seriesList.find((s) => s.seriesId === internalSeriesId && s.observationCount >= 2)?.seriesId) ||
    (propSelectedSeries && propSelectedSeries.observationCount >= 2 ? propSelectedSeries.seriesId : "") ||
    (initialSeriesId && seriesList.find((s) => s.seriesId === initialSeriesId && s.observationCount >= 2)?.seriesId) ||
    seriesList.find((s) => s.observationCount >= 2)?.seriesId ||
    internalSeriesId ||
    propSelectedSeries?.seriesId ||
    initialSeriesId ||
    (seriesList.length > 0 ? seriesList[0].seriesId : "");

  const activeSeries =
    seriesList.find((s) => s.seriesId === seriesId) ||
    propSelectedSeries ||
    null;

  const discoveryPairId = selectedPairSummary?.pairId || "";
  const candidateRegionId = selectedCandidate?.regionId || "";

  const handleSeriesChange = (newId: string) => {
    const selected = seriesList.find((s) => s.seriesId === newId);
    if (selected && selected.observationCount < 2) {
      return;
    }
    setInternalSeriesId(newId);
    setSelectedPairRaw(null);
    setSelectedPairSummary(null);
    setSelectedCandidate(null);
    setLastDossier(null);
    setError(null);
    if (onSelectSeries) {
      onSelectSeries(newId);
    }
  };

  const isFormValid =
    seriesId.length >= 3 && discoveryPairId.length >= 5 && candidateRegionId.length >= 3;

  const handleLaunch = async () => {
    if (!isFormValid || isExecuting) return;

    setIsExecuting(true);
    setError(null);
    setExecutionStage("1/5: Grounding Series & Discovery Pair…");

    const timer1 = setTimeout(() => {
      setExecutionStage("2/5: Extracting Upstream Evidence (M4C-A/B)…");
    }, 400);
    const timer2 = setTimeout(() => {
      setExecutionStage("3/5: Evaluating False-Alarm Screening (M4D)…");
    }, 800);
    const timer3 = setTimeout(() => {
      setExecutionStage("4/5: Temporal Evidence Reasoning (M4E)…");
    }, 1200);

    const request: InvestigationRequest = {
      series_id: seriesId,
      discovery_pair_id: discoveryPairId,
      candidate_region_id: candidateRegionId,
      pairing_strategy: pairingStrategy,
      requested_format: "json",
    };

    try {
      const rawDossier = await executeInvestigation(request);
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);

      setExecutionStage("5/5: Investigation Dossier Assembled");
      const summary = transformInvestigationDossier(rawDossier);
      setLastDossier({ raw: rawDossier, summary });

      if (onInvestigationComplete) {
        onInvestigationComplete(rawDossier, summary);
      }
    } catch (err: any) {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);

      setError({
        code: err.errorCode || "EXECUTION_ERROR",
        message: err.message || "Failed to orchestrate pipeline investigation.",
        stage: err.stage,
      });
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="space-y-6 text-left font-sans">
      {/* Step 1: Series Selector Bar */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div className="flex items-center space-x-2">
            <span className="w-5 h-5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 flex items-center justify-center font-mono text-[11px] font-bold">
              1
            </span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Target Temporal Series
            </h3>
          </div>
          <div className="text-xs font-mono text-slate-400">
            {activeSeries ? `${activeSeries.observationCount} Observations` : "Select a series"}
          </div>
        </div>

        <div className="mt-4 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <select
            value={seriesId}
            onChange={(e) => handleSeriesChange(e.target.value)}
            className="flex-1 bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
          >
            <option value="" disabled>
              Select a series to investigate…
            </option>
            {seriesList.map((s) => {
              const isUnavailable = s.observationCount < 2;
              return (
                <option
                  key={s.seriesId}
                  value={s.seriesId}
                  disabled={isUnavailable}
                  className={isUnavailable ? "text-slate-500 bg-slate-900" : "text-slate-200 bg-slate-950"}
                >
                  {s.seriesId}{" "}
                  {isUnavailable
                    ? "— UNAVAILABLE — 1 epoch / no discovery pair"
                    : `(${s.observationCount} epochs, ${s.timespanDays}d)`}
                </option>
              );
            })}
          </select>

          {activeSeries && (
            <div className="flex items-center space-x-2 text-xs font-mono px-3 py-2 bg-slate-950/60 rounded-xl border border-slate-800 text-slate-300">
              <span className="text-slate-400">Span:</span>
              <span className="text-cyan-300 font-semibold">{activeSeries.startDate}</span>
              <span>→</span>
              <span className="text-emerald-300 font-semibold">{activeSeries.endDate}</span>
            </div>
          )}
        </div>
      </div>

      {/* Step 2: Scene Pair Selector */}
      {seriesId ? (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
          <ScenePairSelector
            seriesId={seriesId}
            selectedPairId={discoveryPairId}
            onSelectPair={(raw, summary) => {
              setSelectedPairRaw(raw);
              setSelectedPairSummary(summary);
              setSelectedCandidate(null);
              setLastDossier(null);
            }}
          />
        </div>
      ) : (
        <div className="bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl p-6 text-center font-mono text-xs text-slate-500">
          Complete Step 1 by selecting a temporal series above.
        </div>
      )}

      {/* Step 3: Candidate Region Selector */}
      {selectedPairRaw ? (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
          <CandidateRegionSelector
            selectedPair={selectedPairRaw}
            selectedRegionId={candidateRegionId}
            onSelectCandidate={(cand) => {
              setSelectedCandidate(cand);
              setLastDossier(null);
            }}
          />
        </div>
      ) : (
        <div className="bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl p-6 text-center font-mono text-xs text-slate-500">
          Complete Step 2 by selecting a discovery scene pair above.
        </div>
      )}

      {/* Step 4: Pipeline Execution Controller */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-4 border-b border-slate-800">
          <div className="flex items-center space-x-2">
            <span className="w-5 h-5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 flex items-center justify-center font-mono text-[11px] font-bold">
              4
            </span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Orchestrate Multi-Temporal Investigation (M4F)
            </h3>
          </div>

          {/* Subsequent Pairing Strategy */}
          <div className="flex items-center space-x-2 font-mono text-xs">
            <span className="text-slate-400 text-[11px]">Subsequent Strategy:</span>
            <div className="flex bg-slate-950 p-0.5 rounded-lg border border-slate-800">
              <button
                onClick={() => setPairingStrategy("baseline")}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                  pairingStrategy === "baseline"
                    ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800/80"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Baseline
              </button>
              <button
                onClick={() => setPairingStrategy("adjacent")}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                  pairingStrategy === "adjacent"
                    ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800/80"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Adjacent
              </button>
            </div>
          </div>
        </div>

        {/* Form Validation & Parameter Summary */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono mb-5">
          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">Target Series</div>
            <div className={`truncate font-medium ${seriesId ? "text-slate-200" : "text-amber-400 italic"}`}>
              {seriesId || "Missing series"}
            </div>
          </div>

          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">Discovery Pair</div>
            <div
              className={`truncate font-medium ${
                discoveryPairId ? "text-slate-200" : "text-amber-400 italic"
              }`}
            >
              {discoveryPairId || "Missing discovery pair"}
            </div>
          </div>

          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold mb-1">Candidate Region</div>
            <div
              className={`truncate font-medium ${
                candidateRegionId ? "text-emerald-400 font-bold" : "text-amber-400 italic"
              }`}
            >
              {candidateRegionId || "Missing candidate region"}
            </div>
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="mb-5 p-4 rounded-xl bg-rose-950/70 border border-rose-800 text-rose-200 font-mono text-xs space-y-1">
            <div className="font-bold flex items-center space-x-2">
              <span>⚠️</span>
              <span>{error.code}</span>
              {error.stage && (
                <span className="px-2 py-0.5 rounded bg-rose-900/60 text-[10px] border border-rose-700">
                  Stage: {error.stage}
                </span>
              )}
            </div>
            <div className="text-rose-300">{error.message}</div>
          </div>
        )}

        {/* Action Button & Progress */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="text-xs font-mono text-slate-400 flex items-center space-x-2">
            {isExecuting ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                <span className="text-cyan-300 font-semibold">{executionStage}</span>
              </>
            ) : isFormValid ? (
              <span className="text-emerald-400 flex items-center space-x-1.5">
                <span>✓</span>
                <span>All parameters validated. Ready for pipeline orchestration.</span>
              </span>
            ) : (
              <span className="text-amber-400">
                Please complete steps 1, 2, and 3 above to enable investigation launch.
              </span>
            )}
          </div>

          <button
            onClick={handleLaunch}
            disabled={!isFormValid || isExecuting}
            className={`px-6 py-2.5 rounded-xl font-mono text-xs font-bold transition-all shadow-lg flex items-center justify-center space-x-2 ${
              isFormValid && !isExecuting
                ? "bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-slate-950 shadow-cyan-500/20 active:scale-98"
                : "bg-slate-800 text-slate-500 border border-slate-700/50 cursor-not-allowed"
            }`}
          >
            {isExecuting ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></span>
                <span>Orchestrating…</span>
              </>
            ) : (
              <>
                <span>🚀</span>
                <span>Launch Investigation</span>
              </>
            )}
          </button>
        </div>

        {/* Milestone D3 Success Result Card */}
        {lastDossier && !isExecuting && (
          <div className="mt-6 pt-6 border-t border-slate-800/90 font-mono animate-fadeIn">
            <div className="rounded-2xl p-5 bg-slate-950/90 border border-emerald-500/40 shadow-xl shadow-emerald-950/20">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3 pb-3 border-b border-slate-800">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  <span className="text-sm font-bold text-white">
                    Investigation Dossier Generated
                  </span>
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                    {lastDossier.raw.status}
                  </span>
                </div>

                <div className="text-xs text-slate-400">
                  Hash: <span className="text-cyan-300 font-bold">{lastDossier.summary.contentHash}</span>
                </div>
              </div>

              {/* High-Impact Result Metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs mb-4">
                <div className="bg-slate-900/80 p-2.5 rounded-xl border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">Investigation ID</div>
                  <div className="font-bold text-cyan-300 truncate" title={lastDossier.summary.investigationId}>
                    {lastDossier.summary.investigationId}
                  </div>
                </div>

                <div className="bg-slate-900/80 p-2.5 rounded-xl border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">Temporal Support</div>
                  <div className="font-bold text-emerald-400 truncate">
                    {lastDossier.summary.supportStatus}
                  </div>
                </div>

                <div className="bg-slate-900/80 p-2.5 rounded-xl border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">Confidence Tier</div>
                  <div className="font-bold text-white uppercase truncate">
                    {lastDossier.summary.confidenceTier}
                  </div>
                </div>

                <div className="bg-slate-900/80 p-2.5 rounded-xl border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">Onset Interval</div>
                  <div className="font-bold text-cyan-300 truncate">
                    {lastDossier.summary.onset.physicalInterval}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400 pt-2 border-t border-slate-900">
                <div>
                  Primary Category:{" "}
                  <span className="text-white font-bold">{lastDossier.summary.category.primary}</span>{" "}
                  • Evaluated Epochs:{" "}
                  <span className="text-emerald-400 font-semibold">
                    {lastDossier.summary.timelineNodes.length}
                  </span>
                </div>
                {onInvestigationComplete && (
                  <button
                    onClick={() => onInvestigationComplete(lastDossier.raw, lastDossier.summary)}
                    className="px-4 py-2 rounded-xl text-xs font-mono font-bold bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-md shadow-cyan-500/20 transition-all cursor-pointer flex items-center space-x-1.5"
                  >
                    <span>📋 View Result Dossier (D4) →</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
