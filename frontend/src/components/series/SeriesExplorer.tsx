import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchSeriesById, fetchSeriesList } from "../../services/api";
import { transformTemporalSeries } from "../../services/transformers";
import type { TemporalSeriesSummary } from "../../types/models";
import { SeriesCard } from "./SeriesCard";
import { SeriesDetail } from "./SeriesDetail";

interface SeriesExplorerProps {
  onLaunchInvestigation?: (seriesId: string) => void;
}

export const SeriesExplorer: React.FC<SeriesExplorerProps> = ({ onLaunchInvestigation }) => {
  const [seriesList, setSeriesList] = useState<TemporalSeriesSummary[]>([]);
  const [selectedSeriesId, setSelectedSeriesId] = useState<string | null>(null);
  const [selectedSeriesDetail, setSelectedSeriesDetail] = useState<TemporalSeriesSummary | null>(null);
  const [isLoadingList, setIsLoadingList] = useState<boolean>(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [onlyMultiEpoch, setOnlyMultiEpoch] = useState<boolean>(false);

  // 1. Fetch selected series detail by ID
  const loadSeriesDetail = useCallback(async (seriesId: string, fallbackList?: TemporalSeriesSummary[]) => {
    setIsLoadingDetail(true);
    try {
      const rawDetail = await fetchSeriesById(seriesId);
      const detailSummary = transformTemporalSeries(rawDetail);
      setSelectedSeriesDetail(detailSummary);
    } catch {
      const fallback = (fallbackList || seriesList).find((s) => s.seriesId === seriesId);
      if (fallback) {
        setSelectedSeriesDetail(fallback);
      }
    } finally {
      setIsLoadingDetail(false);
    }
  }, [seriesList]);

  // 2. Fetch available series list
  const loadSeries = useCallback(async (preferredId?: string) => {
    setIsLoadingList(true);
    setError(null);
    try {
      const rawList = await fetchSeriesList();
      const summaries = rawList.map(transformTemporalSeries);
      setSeriesList(summaries);

      if (summaries.length > 0) {
        const targetId =
          preferredId ||
          selectedSeriesId ||
          summaries.find((s) => s.observationCount >= 4)?.seriesId ||
          summaries[0].seriesId;
        setSelectedSeriesId(targetId);
        await loadSeriesDetail(targetId, summaries);
      } else {
        setSelectedSeriesId(null);
        setSelectedSeriesDetail(null);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load temporal series from API.");
      setSeriesList([]);
    } finally {
      setIsLoadingList(false);
    }
  }, [selectedSeriesId, loadSeriesDetail]);

  useEffect(() => {
    let isMounted = true;
    fetchSeriesList()
      .then(async (rawList) => {
        if (!isMounted) return;
        const summaries = rawList.map(transformTemporalSeries);
        setSeriesList(summaries);
        setIsLoadingList(false);

        if (summaries.length > 0) {
          const targetId =
            summaries.find((s) => s.observationCount >= 4)?.seriesId ||
            summaries[0].seriesId;
          setSelectedSeriesId(targetId);
          setIsLoadingDetail(true);
          try {
            const rawDetail = await fetchSeriesById(targetId);
            if (isMounted) setSelectedSeriesDetail(transformTemporalSeries(rawDetail));
          } catch {
            if (isMounted) setSelectedSeriesDetail(summaries.find((s) => s.seriesId === targetId) || null);
          } finally {
            if (isMounted) setIsLoadingDetail(false);
          }
        }
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Failed to load temporal series from API.");
        setSeriesList([]);
        setIsLoadingList(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectSeries = (seriesId: string) => {
    setSelectedSeriesId(seriesId);
    loadSeriesDetail(seriesId);
  };

  // Filtered series list
  const filteredSeries = useMemo(() => {
    return seriesList.filter((s) => {
      const matchesSearch =
        s.seriesId.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.targetId.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.sensors.some((sens) => sens.toLowerCase().includes(searchTerm.toLowerCase())) ||
        s.platforms.some((plat) => plat.toLowerCase().includes(searchTerm.toLowerCase()));
      const matchesMulti = onlyMultiEpoch ? s.observationCount >= 2 : true;
      return matchesSearch && matchesMulti;
    });
  }, [seriesList, searchTerm, onlyMultiEpoch]);

  return (
    <div className="space-y-6 text-left">
      {/* Explorer Top Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/80 border border-slate-800/90 rounded-2xl p-4 sm:p-5 backdrop-blur-md shadow-lg">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-lg font-bold font-mono text-white tracking-wide">
              Temporal Series Explorer
            </h2>
            <span className="px-2 py-0.5 text-xs font-mono rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              Phase M4A • D2
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Browse ingested multi-temporal satellite series and chronologically ordered observation catalogs.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => loadSeries(selectedSeriesId || undefined)}
            disabled={isLoadingList}
            className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600 transition-colors disabled:opacity-50"
          >
            <span className={isLoadingList ? "animate-spin" : ""}>↻</span>
            <span>{isLoadingList ? "Refreshing…" : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Error state banner */}
      {error && (
        <div className="rounded-xl p-4 bg-rose-950/60 border border-rose-800/80 text-rose-200 font-mono text-xs flex items-start space-x-3 shadow-lg">
          <span className="text-base">⚠️</span>
          <div className="flex-1">
            <div className="font-bold text-rose-100">API Connection Error</div>
            <div className="mt-0.5 text-rose-300">{error}</div>
            <button
              onClick={() => loadSeries()}
              className="mt-2 text-[11px] underline font-semibold hover:text-white"
            >
              Retry Connection
            </button>
          </div>
        </div>
      )}

      {/* Main Explorer Workspace: Master-Detail Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Series Catalog List (4 cols) */}
        <div className="lg:col-span-4 space-y-3">
          <div className="bg-slate-950/80 border border-slate-800 rounded-2xl p-4 shadow-xl">
            {/* Search & Filter Controls */}
            <div className="space-y-2.5 mb-3.5">
              <div className="relative">
                <input
                  type="text"
                  placeholder="Filter series by ID, sensor…"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono focus:outline-none focus:border-cyan-500 transition-colors"
                />
                {searchTerm && (
                  <button
                    onClick={() => setSearchTerm("")}
                    className="absolute right-2.5 top-1.5 text-xs text-slate-400 hover:text-slate-200"
                  >
                    ✕
                  </button>
                )}
              </div>

              <div className="flex items-center justify-between text-xs font-mono text-slate-400 px-1">
                <label className="flex items-center space-x-2 cursor-pointer hover:text-slate-200">
                  <input
                    type="checkbox"
                    checked={onlyMultiEpoch}
                    onChange={(e) => setOnlyMultiEpoch(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0 focus:ring-offset-0"
                  />
                  <span>Multi-epoch only (≥2)</span>
                </label>

                <span>
                  {filteredSeries.length} of {seriesList.length}
                </span>
              </div>
            </div>

            {/* Series Cards Scroll Area */}
            <div className="space-y-2.5 max-h-[640px] overflow-y-auto pr-1 select-none">
              {isLoadingList && seriesList.length === 0 ? (
                <div className="space-y-3 py-2">
                  {[1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 animate-pulse space-y-2"
                    >
                      <div className="h-4 bg-slate-800 rounded w-3/4"></div>
                      <div className="h-3 bg-slate-800/60 rounded w-1/2"></div>
                    </div>
                  ))}
                </div>
              ) : filteredSeries.length === 0 ? (
                <div className="text-center py-10 text-xs font-mono text-slate-400 bg-slate-900/30 rounded-xl border border-slate-800/60">
                  {seriesList.length === 0
                    ? "No temporal series cataloged in backend."
                    : "No series match your search query."}
                </div>
              ) : (
                filteredSeries.map((series) => (
                  <SeriesCard
                    key={series.seriesId}
                    series={series}
                    isSelected={series.seriesId === selectedSeriesId}
                    onSelect={handleSelectSeries}
                  />
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Selected Series Details & Observation Timeline (8 cols) */}
        <div className="lg:col-span-8">
          <SeriesDetail
            series={selectedSeriesDetail}
            isLoading={isLoadingDetail}
            onLaunchInvestigation={onLaunchInvestigation}
          />
        </div>
      </div>
    </div>
  );
};
