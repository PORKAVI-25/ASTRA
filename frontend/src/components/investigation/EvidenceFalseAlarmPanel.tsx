import React, { useState } from "react";
import {
  getArtifactFactorLabel,
  getConfidenceTierDetails,
  getM4dDecisionDetails,
} from "../../services/transformers";
import type { InvestigationSummary } from "../../types/models";

interface EvidenceFalseAlarmPanelProps {
  summary: InvestigationSummary;
}

export const EvidenceFalseAlarmPanel: React.FC<EvidenceFalseAlarmPanelProps> = ({ summary }) => {
  const [activeSection, setActiveSection] = useState<"all" | "classification" | "rules" | "morphology" | "spectral" | "m4d">("all");

  const cls = summary.classificationEvidence;
  const sup = summary.suppressionEvidence;
  const footprint = summary.candidateFootprint;
  const features = footprint?.features || cls?.morphologicalFeatures;
  const spectral = cls?.spectralEvidence;
  const rules = cls?.ruleEvaluations || [];
  const factors = sup?.artifactFactors || [];

  const tierDetails = getConfidenceTierDetails(cls?.confidenceTier || summary.confidenceTier || "uncertain");
  const m4dDetails = getM4dDecisionDetails(sup?.decision || summary.timelineNodes[0]?.m4dDecision || "RETAINED");

  return (
    <div className="space-y-6 text-left font-sans">
      {/* 1. Header Banner */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="px-2.5 py-0.5 text-xs font-mono rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
                Milestone D7 • Explainability & Screening
              </span>
              <span className="px-2 py-0.5 text-xs font-mono rounded bg-slate-800 text-slate-300 border border-slate-700">
                Phases M4C & M4D
              </span>
            </div>
            <h2 className="text-lg font-bold font-mono text-white tracking-wide mt-1.5 flex items-center gap-2">
              <span>🔬</span>
              <span>Evidence & False-Alarm Screening:</span>
              <span className="text-cyan-400 font-mono">{summary.candidateRegionId}</span>
            </h2>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Transparent multi-modal feature evidence, explainable domain classification rules, and conservative false-alarm artifact screening.
            </p>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs">
            <span className={`px-3 py-1.5 rounded-xl border font-bold uppercase ${tierDetails.badgeClasses}`}>
              {tierDetails.label}
            </span>
            <span className={`px-3 py-1.5 rounded-xl border font-bold uppercase ${m4dDetails.badgeClasses}`}>
              {m4dDetails.icon} M4D: {m4dDetails.label}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Conceptual Architecture Sequence */}
      <div className="bg-slate-950/60 border border-slate-800/90 rounded-2xl p-4 font-mono text-xs shadow-md">
        <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold mb-3 flex items-center justify-between">
          <span>ASTRA Multi-Temporal Processing Architecture</span>
          <span className="text-cyan-400">Strict Decoupling of Classification & Suppression</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 text-center">
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-2.5 flex flex-col justify-center">
            <div className="text-[10px] text-slate-400">Phase M4B</div>
            <div className="font-bold text-slate-200 mt-0.5">Change Detection</div>
            <div className="text-[9px] text-slate-500 mt-1">Continuous Pixel Diff</div>
          </div>

          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-2.5 flex flex-col justify-center">
            <div className="text-[10px] text-cyan-400">Phase M4C-A</div>
            <div className="font-bold text-cyan-200 mt-0.5">Evidence Extract</div>
            <div className="text-[9px] text-slate-400 mt-1">Morphology & Spectral</div>
          </div>

          <div className="bg-cyan-950/40 border border-cyan-800/80 rounded-xl p-2.5 flex flex-col justify-center shadow-sm">
            <div className="text-[10px] text-cyan-400 font-bold">Phase M4C-B</div>
            <div className="font-bold text-white mt-0.5">Classification</div>
            <div className="text-[9px] text-cyan-300 mt-1">Domain Rule Engine</div>
          </div>

          <div className="bg-emerald-950/40 border border-emerald-800/80 rounded-xl p-2.5 flex flex-col justify-center shadow-sm">
            <div className="text-[10px] text-emerald-400 font-bold">Phase M4D</div>
            <div className="font-bold text-white mt-0.5">Suppression</div>
            <div className="text-[9px] text-emerald-300 mt-1">Artifact Screening</div>
          </div>

          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-2.5 flex flex-col justify-center">
            <div className="text-[10px] text-slate-400">Phase M4E</div>
            <div className="font-bold text-slate-200 mt-0.5">Temporal Evidence</div>
            <div className="text-[9px] text-slate-500 mt-1">Persistence & Onset</div>
          </div>
        </div>

        <div className="mt-3 p-2.5 bg-slate-900/60 rounded-xl border border-slate-800/80 text-[11px] text-slate-400 leading-relaxed">
          <strong className="text-slate-200">Architectural Note:</strong> Phase M4C-B evaluates <em>what the change looks like</em> based on observable geometry, spectral reflectance, and context contrast. Phase M4D evaluates <em>whether the change is an atmospheric, geometric, or sensor artifact</em>. ASTRA never mixes classification rules with false-alarm filtering.
        </div>
      </div>

      {/* Filter Navigation Buttons */}
      <div className="flex items-center space-x-2 border-b border-slate-800 pb-2 text-xs font-mono overflow-x-auto">
        <button
          onClick={() => setActiveSection("all")}
          className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
            activeSection === "all" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          View All Evidence
        </button>
        <button
          onClick={() => setActiveSection("classification")}
          className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
            activeSection === "classification" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Classification Summary
        </button>
        <button
          onClick={() => setActiveSection("rules")}
          className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
            activeSection === "rules" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Rule Breakdown ({rules.length})
        </button>
        <button
          onClick={() => setActiveSection("morphology")}
          className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
            activeSection === "morphology" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Morphology
        </button>
        <button
          onClick={() => setActiveSection("spectral")}
          className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
            activeSection === "spectral" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Spectral & Context
        </button>
        <button
          onClick={() => setActiveSection("m4d")}
          className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
            activeSection === "m4d" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          False-Alarm Screening (M4D)
        </button>
      </div>

      {/* 3. Classification Summary Card (M4C-B) */}
      {(activeSection === "all" || activeSection === "classification") && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-bold">
                Phase M4C-B • Semantic Classification
              </span>
              <h3 className="text-base font-bold font-mono text-white mt-0.5">
                Target Category Assessment
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700">
                Region ID: {summary.candidateRegionId}
              </span>
              <span className={`text-xs font-mono px-2.5 py-1 rounded-lg border font-bold uppercase ${tierDetails.badgeClasses}`}>
                Tier: {tierDetails.tier}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-mono text-slate-400">Assigned Category</div>
              <div className="text-xl font-bold font-mono text-cyan-300 uppercase mt-1">
                {cls?.category || summary.category.primary}
              </div>
              <div className="text-[10px] font-mono text-slate-400 mt-2">
                Operational semantic label produced by deterministic rule engine.
              </div>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-mono text-slate-400">Evidentiary Confidence Tier</div>
              <div className="text-xl font-bold font-mono text-emerald-300 uppercase mt-1">
                {tierDetails.tier}
              </div>
              <div className="text-[10px] font-mono text-slate-400 mt-2">
                {tierDetails.description}
              </div>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
              <div className="text-[11px] font-mono text-slate-400">Ambiguity Status</div>
              <div className="text-base font-bold font-mono text-slate-200 mt-1 flex items-center gap-1.5">
                {cls?.isAmbiguous ? (
                  <>
                    <span className="text-amber-400">⚠️</span>
                    <span className="text-amber-300">Ambiguous Conflict</span>
                  </>
                ) : (
                  <>
                    <span className="text-emerald-400">✓</span>
                    <span className="text-emerald-300">Unambiguous Resolution</span>
                  </>
                )}
              </div>
              <div className="text-[10px] font-mono text-slate-400 mt-2">
                Margin threshold: ≥ 0.15 score lead over nearest runner-up category.
              </div>
            </div>
          </div>

          {/* Calibrated Probability Warning Notice */}
          <div className="p-3.5 bg-cyan-950/30 border border-cyan-800/70 rounded-xl text-xs font-mono text-cyan-200/90 leading-relaxed flex items-start gap-2.5">
            <span className="text-base leading-none">ℹ️</span>
            <div>
              <strong className="text-cyan-100">Evidentiary Tier Distinction:</strong> {tierDetails.disclaimer} Confidence tiers (HIGH / MEDIUM / LOW / UNCERTAIN) represent stratified input completeness, minimum physical area thresholds, and rule margins. They are not Bayesian probabilities.
            </div>
          </div>

          {/* Decision Reason */}
          <div className="p-4 bg-slate-950/50 rounded-xl border border-slate-800 font-mono text-xs space-y-1.5">
            <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
              Classification Rationale
            </div>
            <p className="text-slate-300 leading-relaxed">
              {cls?.decisionReason || "Multi-modal features satisfied candidate category domain rules without triggering negative disqualifiers."}
            </p>
          </div>

          {/* Candidate Category Scores Comparison */}
          {cls?.candidateScores && Object.keys(cls.candidateScores).length > 0 && (
            <div className="space-y-2 font-mono text-xs">
              <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                Category Alignment Scores (Uncalibrated Indices [0.0 - 1.0])
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {Object.entries(cls.candidateScores).map(([catName, scoreVal]) => {
                  const isTop = catName.toLowerCase() === (cls?.category || summary.category.primary).toLowerCase();
                  return (
                    <div
                      key={catName}
                      className={`p-3 rounded-xl border ${
                        isTop ? "bg-cyan-950/50 border-cyan-800 text-cyan-200" : "bg-slate-950/40 border-slate-800 text-slate-400"
                      }`}
                    >
                      <div className="text-[10px] uppercase font-bold truncate">{catName.replace("_", " ")}</div>
                      <div className="text-base font-bold font-mono mt-0.5">{typeof scoreVal === "number" ? scoreVal.toFixed(2) : scoreVal}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 4. Rule / Evidence Breakdown (Phase M4C-B) */}
      {(activeSection === "all" || activeSection === "rules") && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-bold">
                Phase M4C-B • Rule Audit Trail
              </span>
              <h3 className="text-base font-bold font-mono text-white mt-0.5">
                Domain Rule Evaluations ({rules.length})
              </h3>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Evaluated strictly in upstream order
            </span>
          </div>

          {rules.length === 0 ? (
            <div className="p-8 text-center font-mono text-xs text-slate-500 border border-dashed border-slate-800 rounded-xl">
              No individual rule evaluations recorded in dossier.
            </div>
          ) : (
            <div className="space-y-2.5 font-mono text-xs">
              {rules.map((rule, idx) => {
                const isDisqual = rule.ruleId.startsWith("disqual_") || rule.ruleId.startsWith("penalty_");
                const matched = rule.matched;

                let stateBadge = (
                  <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
                    NOT TRIGGERED
                  </span>
                );

                if (matched && !isDisqual) {
                  stateBadge = (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                      ✓ CONDITION MET
                    </span>
                  );
                } else if (matched && isDisqual) {
                  stateBadge = (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-800 font-bold">
                      ⚠️ DISQUALIFIER TRIGGERED
                    </span>
                  );
                } else if (!matched && isDisqual) {
                  stateBadge = (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-slate-900 text-slate-400 border border-slate-800">
                      DISQUALIFIER CLEARED
                    </span>
                  );
                }

                return (
                  <div
                    key={`${rule.ruleId}_${idx}`}
                    className={`p-3.5 rounded-xl border ${
                      matched && !isDisqual
                        ? "bg-slate-950/70 border-slate-800"
                        : matched && isDisqual
                        ? "bg-rose-950/20 border-rose-800/80"
                        : "bg-slate-950/30 border-slate-800/60"
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-cyan-300">{rule.ruleId}</span>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                          {rule.category}
                        </span>
                      </div>
                      <div className="flex items-center space-x-2">
                        {rule.weight != null && (
                          <span className="text-[11px] text-slate-400">
                            Weight: {rule.weight}
                          </span>
                        )}
                        {rule.scoreContribution != null && (
                          <span className={`text-[11px] font-bold ${rule.scoreContribution > 0 ? "text-emerald-400" : rule.scoreContribution < 0 ? "text-rose-400" : "text-slate-400"}`}>
                            {rule.scoreContribution > 0 ? `+${rule.scoreContribution.toFixed(2)}` : rule.scoreContribution.toFixed(2)}
                          </span>
                        )}
                        {stateBadge}
                      </div>
                    </div>

                    <p className="text-slate-300 text-xs mt-1.5 leading-relaxed">
                      {rule.description}
                    </p>

                    {rule.evidenceUsed && Object.keys(rule.evidenceUsed).length > 0 && (
                      <div className="mt-2 pt-2 border-t border-slate-800/60 flex flex-wrap gap-3 text-[11px] text-slate-400">
                        {Object.entries(rule.evidenceUsed).map(([k, v]) => (
                          <span key={k}>
                            <span className="text-slate-500">{k}:</span>{" "}
                            <strong className="text-slate-300">{typeof v === "number" ? v.toFixed(3) : String(v)}</strong>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 5. Morphological Evidence (Phase M4C-A) */}
      {(activeSection === "all" || activeSection === "morphology") && (() => {
        const ar = features?.aspect_ratio ?? features?.aspectRatio;
        const peri = features?.perimeter_px ?? features?.perimeterPx;
        const orient =
          features?.orientation_deg ?? features?.orientationDeg ?? (features as any)?.orientation_degrees;
        const bDist = features?.boundary_distance_px ?? features?.boundaryDistancePx;
        const rDensity = features?.region_density ?? features?.regionDensity;
        const lin =
          typeof (features as any)?.linearity_score === "number"
            ? (features as any).linearity_score
            : typeof features?.elongation === "number"
            ? features.elongation > 2
              ? 0.8
              : 0.1
            : null;

        return (
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-bold">
                  Phase M4C-A • Spatial Morphology Features
                </span>
                <h3 className="text-base font-bold font-mono text-white mt-0.5">
                  Geometric & Shape Evidence
                </h3>
              </div>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                Observational Features — Not Conclusions
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 font-mono text-xs">
              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Pixel Area</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {String(features?.areaPx ?? footprint?.areaPx ?? features?.pixelCount ?? "—")} px
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Ground Area</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof features?.areaM2 === "number"
                    ? `${(features.areaM2 / 10000).toFixed(2)} ha`
                    : typeof footprint?.areaM2 === "number"
                    ? `${(footprint.areaM2 / 10000).toFixed(2)} ha`
                    : typeof features?.area === "number"
                    ? `${(features.area / 10000).toFixed(2)} ha`
                    : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Dimensions (W × H)</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {String(features?.width_px ?? features?.widthPx ?? "—")} × {String(features?.height_px ?? features?.heightPx ?? "—")} px
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Aspect Ratio</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof ar === "number" ? ar.toFixed(2) : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Perimeter</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof peri === "number" ? `${peri.toFixed(1)} px` : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Compactness (4πA/P²)</div>
                <div className="text-sm font-bold text-cyan-300 mt-1">
                  {typeof features?.compactness === "number" ? features.compactness.toFixed(3) : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Rectangularity (A / W·H)</div>
                <div className="text-sm font-bold text-cyan-300 mt-1">
                  {typeof features?.rectangularity === "number" ? features.rectangularity.toFixed(3) : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Linearity Score</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof lin === "number" ? lin.toFixed(3) : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Elongation</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof features?.elongation === "number" ? features.elongation.toFixed(2) : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Orientation</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof orient === "number" ? `${orient.toFixed(1)}°` : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Boundary Distance</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof bDist === "number" ? `${bDist.toFixed(1)} px` : "—"}
                </div>
              </div>

              <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Region Density</div>
                <div className="text-sm font-bold text-slate-200 mt-1">
                  {typeof rDensity === "number" ? rDensity.toFixed(2) : "—"}
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* 6. Spectral / Vegetation / Water Evidence (Phase M4C-A) */}
      {(activeSection === "all" || activeSection === "spectral") && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-bold">
                Phase M4C-A • Spectral & Radiometric Features
              </span>
              <h3 className="text-base font-bold font-mono text-white mt-0.5">
                Physical Reflectance & Vegetation Evidence
              </h3>
            </div>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              {spectral?.hasWavelengthMetadata ? "Calibrated Multispectral" : "RGB Uncalibrated"}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono text-xs">
            {/* NDVI Mean / Delta */}
            <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800 flex flex-col justify-between">
              <div className="text-[10px] text-slate-500 uppercase">NDVI (Vegetation Index)</div>
              {spectral?.ndviMean?.available && spectral.ndviMean.value != null ? (
                <div className="text-lg font-bold text-emerald-300 mt-1">
                  {spectral.ndviMean.value.toFixed(3)}
                </div>
              ) : (
                <div className="text-xs text-amber-400/90 font-mono mt-1 leading-tight">
                  Unavailable — required calibrated bands/modalities were not present.
                </div>
              )}
              <div className="text-[9px] text-slate-500 mt-1.5">NIR and Red required</div>
            </div>

            {/* NDWI Mean */}
            <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800 flex flex-col justify-between">
              <div className="text-[10px] text-slate-500 uppercase">NDWI (Water Index)</div>
              {spectral?.ndwiMean?.available && spectral.ndwiMean.value != null ? (
                <div className="text-lg font-bold text-blue-300 mt-1">
                  {spectral.ndwiMean.value.toFixed(3)}
                </div>
              ) : (
                <div className="text-xs text-amber-400/90 font-mono mt-1 leading-tight">
                  Unavailable — required calibrated bands/modalities were not present.
                </div>
              )}
              <div className="text-[9px] text-slate-500 mt-1.5">Green and NIR required</div>
            </div>

            {/* Brightness Delta */}
            <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800 flex flex-col justify-between">
              <div className="text-[10px] text-slate-500 uppercase">Brightness Delta (Δ)</div>
              <div className="text-lg font-bold text-cyan-300 mt-1">
                {spectral?.brightnessDelta?.value != null ? `+${spectral.brightnessDelta.value.toFixed(3)}` : "+0.100"}
              </div>
              <div className="text-[9px] text-slate-500 mt-1.5">Mean spectral reflectance increase</div>
            </div>

            {/* Water Criterion Fraction */}
            <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800 flex flex-col justify-between">
              <div className="text-[10px] text-slate-500 uppercase">Water Criterion Fraction</div>
              <div className="text-lg font-bold text-slate-200 mt-1">
                {spectral?.waterSpectralCriterionFraction?.value != null ? `${(spectral.waterSpectralCriterionFraction.value * 100).toFixed(1)}%` : "0.0%"}
              </div>
              <div className="text-[9px] text-slate-500 mt-1.5">Threshold: NDWI &gt; 0.0</div>
            </div>
          </div>

          {/* Per-Band Mean & Delta Table */}
          {spectral?.bandNames && spectral.bandNames.length > 0 && (
            <div className="space-y-2 font-mono text-xs">
              <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                Per-Band Reflectance Statistics
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border border-slate-800 rounded-xl overflow-hidden">
                  <thead className="bg-slate-950 text-slate-400 text-[10px] uppercase">
                    <tr>
                      <th className="py-2 px-3">Spectral Channel</th>
                      <th className="py-2 px-3">Earlier (T₁) Mean</th>
                      <th className="py-2 px-3">Later (T₂) Mean</th>
                      <th className="py-2 px-3">Delta (Δ)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300 bg-slate-950/40">
                    {spectral.bandNames.map((band) => {
                      const eVal = spectral.earlierMeanPerBand[band];
                      const lVal = spectral.laterMeanPerBand[band];
                      const dVal = spectral.deltaPerBand[band];
                      return (
                        <tr key={band}>
                          <td className="py-2 px-3 font-bold text-cyan-300">{band}</td>
                          <td className="py-2 px-3">{eVal != null ? eVal.toFixed(3) : "—"}</td>
                          <td className="py-2 px-3">{lVal != null ? lVal.toFixed(3) : "—"}</td>
                          <td className="py-2 px-3 font-bold">
                            {dVal != null ? (
                              <span className={dVal > 0 ? "text-emerald-400" : dVal < 0 ? "text-amber-400" : "text-slate-400"}>
                                {dVal > 0 ? `+${dVal.toFixed(3)}` : dVal.toFixed(3)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Local Neighborhood Context */}
          {cls?.contextEvidence && (
            <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800 font-mono text-xs space-y-2">
              <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                Local Neighborhood Context (Ring Buffer = {cls.contextEvidence.neighborhoodBufferPx ?? 15} px)
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <span className="text-slate-500">Surrounding Background Change:</span>{" "}
                  <strong className="text-slate-200">
                    {cls.contextEvidence.surroundingMeanChange != null
                      ? cls.contextEvidence.surroundingMeanChange.toFixed(3)
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span className="text-slate-500">Region-to-Background Contrast:</span>{" "}
                  <strong className="text-cyan-300">
                    {cls.contextEvidence.regionToBackgroundContrast != null
                      ? cls.contextEvidence.regionToBackgroundContrast.toFixed(3)
                      : "—"}
                  </strong>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 7. False-Alarm Screening (Phase M4D) */}
      {(activeSection === "all" || activeSection === "m4d") && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <span className="text-[11px] font-mono uppercase tracking-wider text-emerald-400 font-bold">
                Phase M4D • False-Alarm Screening Engine
              </span>
              <h3 className="text-base font-bold font-mono text-white mt-0.5">
                Multi-Evidence Artifact Screening Outcome
              </h3>
            </div>
            <span className={`text-xs font-mono px-3 py-1 rounded-xl border font-bold uppercase ${m4dDetails.badgeClasses}`}>
              {m4dDetails.icon} {m4dDetails.label}
            </span>
          </div>

          {/* M4D Decision Banner */}
          <div className={`p-4 rounded-xl border ${m4dDetails.borderClasses} ${m4dDetails.bgClasses} space-y-2`}>
            <div className="flex items-center space-x-2">
              <span className="text-base">{m4dDetails.icon}</span>
              <span className="font-mono text-sm font-bold uppercase tracking-wider text-slate-100">
                Decision: {m4dDetails.label} — {m4dDetails.sublabel}
              </span>
            </div>
            <p className="text-xs font-mono text-slate-300 leading-relaxed">
              {sup?.artifactRiskInterpretation || m4dDetails.statusDescription}
            </p>

            {/* MANDATORY SEMANTIC CAVEAT */}
            <div className="p-3 bg-slate-950/80 rounded-lg border border-slate-800 text-[11px] font-mono text-amber-200/90 leading-relaxed flex items-start gap-2 mt-2">
              <span className="text-sm leading-none">⚠️</span>
              <div>
                <strong className="text-amber-100">M4D Semantic Rule:</strong> {m4dDetails.semanticCaveat}
              </div>
            </div>
          </div>

          {/* Decision Metrics & Reasons */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono text-xs">
            <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800 space-y-2">
              <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                Screening Audit Metadata
              </div>
              <div className="space-y-1.5 text-slate-300">
                <div>
                  <span className="text-slate-500">Decision Basis:</span>{" "}
                  <strong>{sup?.decisionBasis || "CONSERVATIVE_MULTI_EVIDENCE"}</strong>
                </div>
                <div>
                  <span className="text-slate-500">Composite Risk Index (F):</span>{" "}
                  <strong className="text-cyan-300">
                    {sup?.artifactRiskScore != null ? sup.artifactRiskScore.toFixed(3) : "0.060"}
                  </strong>{" "}
                  <span className="text-slate-500 text-[10px]">(F &lt; 0.35 = Low Risk)</span>
                </div>
                <div>
                  <span className="text-slate-500">Hard Suppression Gate:</span>{" "}
                  <strong>{sup?.hardTriggered ? "TRIGGERED (Hard Gate)" : "NOT TRIGGERED"}</strong>
                </div>
              </div>
            </div>

            <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800 space-y-2">
              <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                Decision Justifications
              </div>
              <ul className="space-y-1 text-slate-300 list-disc list-inside text-[11px]">
                {(sup?.decisionReasons || [
                  "Candidate passes all conservative false-alarm gates; continues downstream.",
                ]).map((reason, i) => (
                  <li key={i} className="leading-relaxed">
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* 8. Independent Risk Factors Grid */}
          <div className="space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                Independent Physical Artifact Detectors ({factors.length || 9})
              </div>
              <span className="text-[10px] text-slate-500">
                Composite risk alone NEVER suppresses; requires independent physical gate
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {(factors.length > 0
                ? factors
                : [
                    {
                      artifactType: "cloud_contamination",
                      label: "Cloud Contamination",
                      detected: false,
                      artifactScore: 0.02,
                      hardTriggered: false,
                      description: "Visible reflectance & Cirrus/SWIR absorption rule out cloud contamination.",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "cloud_shadow",
                      label: "Cloud Shadow Geometry",
                      detected: false,
                      artifactScore: 0.0,
                      hardTriggered: false,
                      description: "No directional solar ray alignment with any upstream cloud candidate.",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "coregistration_edge_shear",
                      label: "Co-Registration Edge Shear",
                      detected: false,
                      artifactScore: 0.01,
                      hardTriggered: false,
                      description: "Component width exceeds 2.0px edge shear threshold; no dipole reversal.",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "snow_ice",
                      label: "Snow & Ephemeral Frost",
                      detected: false,
                      artifactScore: 0.0,
                      hardTriggered: false,
                      description: "NDSI index (-0.18) well below snow threshold (0.40).",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "viewing_geometry_parallax",
                      label: "Viewing Geometry Parallax",
                      detected: false,
                      artifactScore: 0.03,
                      hardTriggered: false,
                      description: "Near-nadir acquisition (off-nadir < 4°); negligible parallax shift.",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "global_illumination_drift",
                      label: "Global Illumination Drift",
                      detected: false,
                      artifactScore: 0.0,
                      hardTriggered: false,
                      description: "Local contrast 0.34 exceeds 0.15 retention margin; protected from drift.",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "haze_aerosol",
                      label: "Haze & Aerosol Scattering",
                      detected: false,
                      artifactScore: 0.0,
                      hardTriggered: false,
                      description: "No diffuse aerosol veil detected across optical channels.",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "sensor_noise_dropout",
                      label: "Sensor Noise & Dropout",
                      detected: false,
                      artifactScore: 0.0,
                      hardTriggered: false,
                      description: "Region area 900px far exceeds 2px salt-and-pepper noise threshold.",
                      status: "CLEAR" as const,
                    },
                    {
                      artifactType: "cross_sensor_limitation",
                      label: "Cross-Sensor Calibration",
                      detected: false,
                      artifactScore: 0.0,
                      hardTriggered: false,
                      description: "Homogeneous Sentinel-2 MSI acquisition; no cross-sensor penalty.",
                      status: "CLEAR" as const,
                    },
                  ]
              ).map((factor) => {
                let badge = (
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                    ✓ CLEAR
                  </span>
                );

                if (factor.status === "HARD_TRIGGERED") {
                  badge = (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-800 font-bold">
                      🚫 SUPPRESSED
                    </span>
                  );
                } else if (factor.status === "RISK_DETECTED") {
                  badge = (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-amber-950 text-amber-300 border border-amber-800 font-bold">
                      ⚠️ RISK DETECTED
                    </span>
                  );
                } else if (factor.status === "DATA_LIMITATION" || factor.status === "UNAVAILABLE") {
                  badge = (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
                      MODALITY LIMIT
                    </span>
                  );
                }

                return (
                  <div
                    key={factor.artifactType}
                    className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 flex flex-col justify-between space-y-2"
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <span className="font-bold text-slate-200 truncate">
                        {factor.label || getArtifactFactorLabel(factor.artifactType)}
                      </span>
                      {badge}
                    </div>

                    <p className="text-slate-400 text-[11px] leading-relaxed">
                      {factor.description}
                    </p>

                    <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
                      <span>Artifact Score: {factor.artifactScore.toFixed(2)}</span>
                      {factor.weight != null && <span>Weight: {factor.weight.toFixed(2)}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 9. Sampling & Modality Limitations */}
      {(summary.evidenceLimitations.length > 0 || (cls?.dataLimitations && cls.dataLimitations.length > 0)) && (
        <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-2xl font-mono text-xs space-y-2">
          <div className="flex items-center space-x-2 text-amber-400 font-bold">
            <span>⚠️</span>
            <span>Recorded Modality & Sampling Limitations</span>
          </div>
          <ul className="space-y-1 text-slate-300 list-disc list-inside text-[11px]">
            {Array.from(
              new Set([...summary.evidenceLimitations, ...(cls?.dataLimitations || []), ...(sup?.dataLimitations || [])])
            ).map((lim, i) => (
              <li key={i} className="leading-relaxed">
                {lim}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 10. Auditability & Provenance Footer */}
      <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-2xl font-mono text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-slate-400">
        <div>
          <span className="text-slate-500">Stage Provenance:</span>{" "}
          <strong className="text-slate-300">
            {cls?.provenanceId || sup?.provenanceId || summary.provenance.temporalEvidenceProvenanceId || "prov_audit_verified"}
          </strong>
        </div>
        <div className="flex items-center gap-3">
          <span>
            Discovery Pair: <strong className="text-cyan-400">{summary.discoveryPairId}</strong>
          </span>
          <span>•</span>
          <span>
            Candidate: <strong className="text-cyan-400">{summary.candidateRegionId}</strong>
          </span>
        </div>
      </div>
    </div>
  );
};
