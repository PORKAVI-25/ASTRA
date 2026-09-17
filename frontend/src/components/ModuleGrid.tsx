import React from "react";

interface ModuleInfo {
  key: string;
  name: string;
  description: string;
  phase: string;
  ruleAnchor: string;
  badgeColor: string;
}

const MODULES: ModuleInfo[] = [
  {
    key: "api",
    name: "API & Telemetry",
    description: "FastAPI REST dispatcher, CORS isolation, and health diagnostic subsystem.",
    phase: "Phase 0 - Active",
    ruleAnchor: "Modular Monolith (ADR-001)",
    badgeColor: "text-emerald-400 bg-emerald-950/60 border-emerald-800",
  },
  {
    key: "ingestion",
    name: "Ingestion & Tiling",
    description: "GeoTIFF/COG parser, chip slicing, deterministic tile_id assignment.",
    phase: "Phase 0 - Foundation",
    ruleAnchor: "Stable Tile Identity (Rule 3)",
    badgeColor: "text-cyan-400 bg-cyan-950/60 border-cyan-800",
  },
  {
    key: "retrieval",
    name: "Semantic Retrieval",
    description: "Decoupled embedding adapters, FAISS local vector similarity indexing.",
    phase: "Phase 1 - Target",
    ruleAnchor: "Model Adapters (Rule 6)",
    badgeColor: "text-indigo-400 bg-indigo-950/60 border-indigo-800",
  },
  {
    key: "change_analysis",
    name: "Change Analysis",
    description: "Multi-temporal pixel-level difference maps and transition categorization.",
    phase: "Phase 2 - Target",
    ruleAnchor: "Multi-Temporal (PS227)",
    badgeColor: "text-purple-400 bg-purple-950/60 border-purple-800",
  },
  {
    key: "provenance",
    name: "Provenance & Lineage",
    description: "Cryptographic parent scene links, CRS, bounding boxes, and SHA-256 signatures.",
    phase: "Phase 0 - Foundation",
    ruleAnchor: "Scene Linkage (Rule 4 & 5)",
    badgeColor: "text-emerald-400 bg-emerald-950/60 border-emerald-800",
  },
  {
    key: "evaluation",
    name: "Scientific Evaluation",
    description: "Verifiable mAP, IoU, and Precision@K benchmarking against ground truth.",
    phase: "Phase 0 - Foundation",
    ruleAnchor: "Zero Fabrication (Rule 8)",
    badgeColor: "text-amber-400 bg-amber-950/60 border-amber-800",
  },
];

interface ModuleGridProps {
  moduleStates?: Record<string, string>;
}

export const ModuleGrid: React.FC<ModuleGridProps> = ({ moduleStates }) => {
  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-slate-100">Modular Monolith Architecture</h2>
          <p className="text-xs text-slate-400">
            Strict separation of concerns without microservice network overhead (Anti-Bloat Guardrail)
          </p>
        </div>
        <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
          6 Core Subsystems
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {MODULES.map((mod) => {
          const runtimeState = moduleStates ? moduleStates[mod.key] : null;

          return (
            <div
              key={mod.key}
              className="p-5 rounded-xl bg-slate-900/50 border border-slate-800/80 hover:border-slate-700 transition duration-150 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between">
                  <h3 className="text-sm font-semibold text-white font-mono">{mod.name}</h3>
                  <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${mod.badgeColor}`}>
                    {runtimeState ? `State: ${runtimeState}` : mod.phase}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">{mod.description}</p>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-800/50 flex items-center justify-between text-[11px]">
                <span className="text-slate-500 font-mono">Enforces:</span>
                <span className="text-slate-300 font-mono text-[11px] bg-slate-950/60 px-2 py-0.5 rounded border border-slate-800">
                  {mod.ruleAnchor}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
