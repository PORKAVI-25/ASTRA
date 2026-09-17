import React, { useState } from "react";

const CONTRACT_SAMPLES = {
  tile_manifest: {
    tile_id: "tile_S2A_T43PGQ_x004_y008_z14",
    source_scene_id: "S2A_MSIL2A_20260315T052021_N0500_R019_T43PGQ",
    tile_col: 4,
    tile_row: 8,
    zoom_level: 14,
    dimensions: { width_px: 512, height_px: 512, channels: 3 },
    crs: "EPSG:32643",
    bounds_wgs84: { min_lon: 77.0123, min_lat: 11.4501, max_lon: 77.0582, max_lat: 11.496 },
    acquisition_time: "2026-03-15T05:20:21Z",
    sensor: "Sentinel-2A MSI",
    file_path: "data/processed/tiles/tile_S2A_T43PGQ_x004_y008_z14.png",
    sha256_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    is_synthetic: false,
  },
  provenance_record: {
    provenance_id: "prov_9d8e7f6a5b4c3d2e",
    target_tile_id: "tile_S2A_T43PGQ_x004_y008_z14",
    source_scene_id: "S2A_MSIL2A_20260315T052021_N0500_R019_T43PGQ",
    processing_stage: "chipping_and_normalization",
    pipeline_version: "0.1.0",
    parameters: { chip_size: 512, stride: 512, normalization: "min_max_2_98" },
    executed_by: "astra.ingestion.chipper",
    timestamp: "2026-09-16T10:02:00Z",
  },
  scene_manifest: {
    scene_id: "S2A_MSIL2A_20260315T052021_N0500_R019_T43PGQ",
    sensor: "Sentinel-2A MSI",
    platform: "Sentinel-2",
    acquisition_time: "2026-03-15T05:20:21Z",
    crs: "EPSG:32643",
    bounds_wgs84: { min_lon: 76.842, min_lat: 11.231, max_lon: 77.891, max_lat: 12.215 },
    spatial_resolution_m: 10.0,
    cloud_cover_percentage: 2.4,
    bands: ["B02", "B03", "B04", "B08"],
    source_file_path: "data/raw/S2A_20260315_T43PGQ.tif",
    is_synthetic: false,
    created_at: "2026-09-16T10:00:00Z",
  },
};

export const DataContractsPreview: React.FC = () => {
  const [activeTab, setActiveTab] = useState<keyof typeof CONTRACT_SAMPLES>("tile_manifest");

  return (
    <div className="mt-8 bg-slate-900/60 border border-slate-800 rounded-xl p-6 backdrop-blur-sm shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800/80 gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-100 flex items-center space-x-2">
            <span>Data Contract Inspector (ASTRA-DC-v0.1)</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Preserving CRS, bounding boxes, timestamps, and cryptographic scene-tile linkages (Rules 3, 4, 5, 9)
          </p>
        </div>

        <div className="flex items-center space-x-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800 self-start sm:self-auto">
          {(
            [
              ["tile_manifest", "Tile Manifest (Rule 3 & 4)"],
              ["provenance_record", "Provenance (Rule 5)"],
              ["scene_manifest", "Scene Manifest"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-3 py-1 text-xs font-mono rounded-md transition ${
                activeTab === key
                  ? "bg-slate-800 text-cyan-300 font-medium border border-slate-700 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <div className="bg-slate-950 rounded-lg p-4 border border-slate-800/80 font-mono text-xs overflow-x-auto text-emerald-300">
          <pre>{JSON.stringify(CONTRACT_SAMPLES[activeTab], null, 2)}</pre>
        </div>
      </div>
    </div>
  );
};
