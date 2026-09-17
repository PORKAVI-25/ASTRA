import React, { useEffect, useState } from "react";
import { getChangeMaskUrl, runChangeDetection } from "../../services/api";
import { transformCandidateChange } from "../../services/transformers";
import type { ChangeDetectionResult, ScenePair } from "../../types/api";
import type { CandidateChange } from "../../types/models";

interface CandidateRegionSelectorProps {
  selectedPair: ScenePair | null;
  selectedRegionId: string | null;
  onSelectCandidate: (candidate: CandidateChange) => void;
}

export const CandidateRegionSelector: React.FC<CandidateRegionSelectorProps> = ({
  selectedPair,
  selectedRegionId,
  onSelectCandidate,
}) => {
  const [detectionResult, setDetectionResult] = useState<ChangeDetectionResult | null>(null);
  const [candidates, setCandidates] = useState<CandidateChange[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showMaskPreview, setShowMaskPreview] = useState<boolean>(false);

  const onSelectCandidateRef = React.useRef(onSelectCandidate);
  useEffect(() => {
    onSelectCandidateRef.current = onSelectCandidate;
  });

  const handleManualRerun = () => {
    if (!selectedPair) return;
    setIsLoading(true);
    setError(null);
    runChangeDetection({ pair: selectedPair })
      .then((res) => {
        setDetectionResult(res);
        const mapped = (res.regions || []).map((r) =>
          transformCandidateChange(r, selectedPair.pair_id)
        );
        setCandidates(mapped);
        if (mapped.length > 0) {
          const target =
            mapped.find((c) => c.regionId === "reg_0002") ||
            mapped.find((c) => c.regionId === "reg_0001") ||
            mapped[0];
          onSelectCandidateRef.current(target);
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Change detection failed on selected pair.");
        setDetectionResult(null);
        setCandidates([]);
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  useEffect(() => {
    if (!selectedPair) return;

    let isMounted = true;

    runChangeDetection({ pair: selectedPair })
      .then((res) => {
        if (!isMounted) return;
        setDetectionResult(res);
        setError(null);
        const mapped = (res.regions || []).map((r) =>
          transformCandidateChange(r, selectedPair.pair_id)
        );
        setCandidates(mapped);
        setIsLoading(false);

        if (mapped.length > 0) {
          const target =
            mapped.find((c) => c.regionId === "reg_0002") ||
            mapped.find((c) => c.regionId === "reg_0001") ||
            mapped[0];
          onSelectCandidateRef.current(target);
        }
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Change detection failed on selected pair.");
        setDetectionResult(null);
        setCandidates([]);
        setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedPair]);

  if (!selectedPair) {
    return (
      <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-8 text-center font-mono text-xs text-slate-400">
        Select a discovery scene pair in step 2 to run M4B change detection and extract candidate regions.
      </div>
    );
  }

  const effectiveResult = selectedPair ? detectionResult : null;
  const effectiveCandidates = selectedPair ? candidates : [];
  const maskUrl = effectiveResult?.result_id ? getChangeMaskUrl(effectiveResult.result_id) : null;

  return (
    <div className="space-y-4 text-left font-sans">
      {/* Step Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <span className="w-5 h-5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 flex items-center justify-center font-mono text-[11px] font-bold">
              3
            </span>
            <h3 className="text-sm font-bold font-mono text-white tracking-wide">
              Ground Investigation Candidate Region
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5 ml-7">
            Spatially coherent change connected components detected via M4B pixel differencing.
          </p>
        </div>

        <div className="flex items-center space-x-2 self-start sm:self-auto font-mono text-xs">
          {maskUrl && (
            <button
              onClick={() => setShowMaskPreview(!showMaskPreview)}
              className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 transition-colors"
            >
              {showMaskPreview ? "Hide Mask" : "Preview Mask"}
            </button>
          )}
          <button
            onClick={handleManualRerun}
            disabled={isLoading}
            className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors disabled:opacity-50"
          >
            {isLoading ? "Running…" : "Re-run M4B"}
          </button>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="py-8 text-center font-mono text-xs text-slate-400 space-y-2 animate-pulse">
          <div className="w-6 h-6 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <div>Executing M4B change detection & component analysis…</div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-xl text-rose-300 text-xs font-mono">
          ⚠️ {error}
        </div>
      )}

      {/* Mask Preview Drawer if toggled */}
      {showMaskPreview && maskUrl && (
        <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center font-mono text-xs">
          <div className="text-slate-300 font-semibold mb-2">
            M4B Binary Change Mask • {effectiveResult?.result_id}
          </div>
          <div className="inline-block p-2 bg-black rounded-lg border border-slate-800 max-w-sm">
            <img
              src={maskUrl}
              alt="Binary Change Mask"
              className="w-64 h-64 object-contain rounded border border-slate-900"
            />
          </div>
          <p className="text-[10px] text-slate-400 mt-2">
            White pixels represent detected change above Otsu cutoff threshold (
            {effectiveResult?.metrics.threshold_used}).
          </p>
        </div>
      )}

      {/* Detection Metrics Summary */}
      {effectiveResult && !isLoading && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono">
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold">Regions Detected</div>
            <div className="text-cyan-300 font-bold text-sm">
              {effectiveResult.metrics.number_of_regions}
            </div>
          </div>
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold">Changed Pixels</div>
            <div className="text-slate-200 font-bold text-sm">
              {effectiveResult.metrics.changed_pixels.toLocaleString()} px
            </div>
          </div>
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold">Surface Area</div>
            <div className="text-emerald-300 font-bold text-sm">
              {effectiveResult.metrics.changed_area_m2
                ? `${(effectiveResult.metrics.changed_area_m2 / 10000).toFixed(1)} ha`
                : `${effectiveResult.metrics.changed_area_px} px`}
            </div>
          </div>
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800/80">
            <div className="text-[10px] uppercase text-slate-400 font-semibold">Execution Time</div>
            <div className="text-slate-200 font-bold text-sm">
              {effectiveResult.execution_time_ms} ms
            </div>
          </div>
        </div>
      )}

      {/* Candidate Regions List */}
      {!isLoading && !error && (
        <div className="space-y-2.5">
          {effectiveCandidates.length === 0 ? (
            <div className="py-8 text-center font-mono text-xs text-slate-400 bg-slate-900/40 rounded-xl border border-slate-800">
              No change regions detected in this discovery pair.
            </div>
          ) : (
            effectiveCandidates.map((cand) => {
              const isSelected = cand.regionId === selectedRegionId;
              const bbox = cand.bboxPx;
              const wgs = cand.bboxWgs84;

              return (
                <div
                  key={cand.regionId}
                  onClick={() => onSelectCandidate(cand)}
                  className={`cursor-pointer rounded-xl p-3.5 border transition-all duration-150 font-mono text-xs ${
                    isSelected
                      ? "bg-slate-900/95 border-cyan-500 shadow-md shadow-cyan-950/40 ring-1 ring-cyan-500/30"
                      : "bg-slate-900/60 hover:bg-slate-900/80 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-slate-800/80">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                          isSelected ? "bg-cyan-400 animate-pulse" : "bg-slate-600"
                        }`}
                      ></span>
                      <span className="text-sm font-bold text-white tracking-wide">
                        {cand.regionId}
                      </span>
                      {cand.isTargetCandidate && (
                        <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
                          Recommended Target
                        </span>
                      )}
                    </div>

                    <div className="flex items-center space-x-2">
                      <span className="text-slate-400 text-[11px]">
                        Peak Score:{" "}
                        <span className="text-emerald-400 font-bold">
                          {cand.maxChangeScore.toFixed(3)}
                        </span>
                      </span>
                      <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-200 border border-slate-700">
                        {cand.pixelCount} px
                      </span>
                    </div>
                  </div>

                  {/* Coordinates & Geometry Details */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                    <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
                      <div className="text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
                        Pixel Bounding Box
                      </div>
                      <div className="text-slate-300">
                        [{bbox.minRow}, {bbox.minCol}] to [{bbox.maxRow}, {bbox.maxCol}]
                      </div>
                      <div className="text-[10px] text-slate-400 mt-0.5">
                        Dimensions: {bbox.widthPx} × {bbox.heightPx} px • Centroid: [
                        {cand.centroidPx[0].toFixed(1)}, {cand.centroidPx[1].toFixed(1)}]
                      </div>
                    </div>

                    <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
                      <div className="text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
                        Geographic Extent (WGS84)
                      </div>
                      {wgs ? (
                        <div className="text-slate-300">
                          Lon: [{wgs.minLon.toFixed(4)}°, {wgs.maxLon.toFixed(4)}°]
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            Lat: [{wgs.minLat.toFixed(4)}°, {wgs.maxLat.toFixed(4)}°]
                          </div>
                        </div>
                      ) : (
                        <div className="text-slate-400 italic">Projected from pixel grid</div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};
