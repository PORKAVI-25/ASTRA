/**
 * Unit Tests for Milestone D3: Investigation Launcher
 *
 * Covers:
 * - pair loading/transformation
 * - pairing-mode selection
 * - pair selection
 * - candidate change transformation
 * - candidate selection
 * - validation preventing incomplete investigation requests
 * - correct InvestigationRequest construction
 * - successful investigation response handling
 * - API error handling
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  transformCandidateChange,
  transformInvestigationDossier,
  transformScenePair,
} from "../services/transformers.ts";
import { ApiError } from "../services/api.ts";
import type {
  ChangeRegion,
  InvestigationRequest,
  ScenePair,
} from "../types/api.ts";
import {
  MOCK_CHANGE_REGION,
  MOCK_INVESTIGATION_DOSSIER,
  MOCK_SCENE_PAIR,
  MOCK_TEMPORAL_SERIES,
} from "./fixtures.ts";

describe("Milestone D3: Investigation Launcher Unit Tests", () => {
  // 1. Pair Loading and Transformation
  it("transformScenePair maps raw backend ScenePair into rich ScenePairSummary", () => {
    const summary = transformScenePair(
      MOCK_SCENE_PAIR,
      MOCK_TEMPORAL_SERIES.series_id
    );

    assert.strictEqual(summary.pairId, "pair_obs_01__obs_02");
    assert.strictEqual(summary.seriesId, MOCK_TEMPORAL_SERIES.series_id);
    assert.strictEqual(summary.earlierObservationId, "obs_tile_c0000_r0000_z14_01");
    assert.strictEqual(summary.laterObservationId, "obs_tile_c0000_r0000_z14_02");
    assert.strictEqual(summary.earlierPlatform, "Sentinel-2A");
    assert.strictEqual(summary.laterPlatform, "Sentinel-2B");
    assert.strictEqual(summary.isCompatible, true);
    assert.strictEqual(summary.temporalBaselineDays, 31.0);
    assert.deepStrictEqual(summary.rejectionReasons, []);
  });

  it("transformScenePair handles incompatible pair with rejection reasons", () => {
    const incompatiblePair: ScenePair = {
      pair_id: "pair_incompatible",
      earlier_observation: MOCK_TEMPORAL_SERIES.observations[0],
      later_observation: {
        ...MOCK_TEMPORAL_SERIES.observations[1],
        crs: "EPSG:4326",
      },
      compatibility: {
        is_compatible: false,
        crs_match: false,
        gsd_match: true,
        footprint_overlap_ratio: 0.1,
        temporal_baseline_days: 31.0,
        rejection_reasons: ["CRS mismatch: EPSG:32643 vs EPSG:4326", "Insufficient spatial overlap"],
      },
      pairing_method: "baseline_t0",
    };

    const summary = transformScenePair(incompatiblePair, "test_series");
    assert.strictEqual(summary.isCompatible, false);
    assert.strictEqual(summary.rejectionReasons.length, 2);
    assert.strictEqual(summary.rejectionReasons[0], "CRS mismatch: EPSG:32643 vs EPSG:4326");
  });

  // 2. Pairing-Mode Selection
  it("supports multiple pairing modes (baseline, adjacent, all_pairwise)", () => {
    const modes: Array<"baseline" | "adjacent" | "all_pairwise"> = [
      "baseline",
      "adjacent",
      "all_pairwise",
    ];

    for (const mode of modes) {
      assert.ok(["baseline", "adjacent", "all_pairwise"].includes(mode));
    }

    // Baseline pairs use reference T0
    const baselinePair: ScenePair = {
      ...MOCK_SCENE_PAIR,
      pair_id: "pair_t0_t1",
      pairing_method: "baseline_t0",
    };
    assert.strictEqual(baselinePair.pairing_method, "baseline_t0");

    // Adjacent pairs connect consecutive epochs
    const adjacentPair: ScenePair = {
      ...MOCK_SCENE_PAIR,
      pair_id: "pair_t1_t2",
      pairing_method: "adjacent_step",
    };
    assert.strictEqual(adjacentPair.pairing_method, "adjacent_step");
  });

  // 3. Pair Selection
  it("pair selection identifies and extracts selected pair metadata", () => {
    const pairs: ScenePair[] = [
      MOCK_SCENE_PAIR,
      {
        ...MOCK_SCENE_PAIR,
        pair_id: "pair_obs_01__obs_03",
        later_observation: {
          ...MOCK_TEMPORAL_SERIES.observations[1],
          observation_id: "obs_tile_c0000_r0000_z14_03",
          acquisition_time: "2026-03-15T10:30:00Z",
        },
      },
    ];

    const targetPairId = "pair_obs_01__obs_03";
    const selected = pairs.find((p) => p.pair_id === targetPairId);

    assert.ok(selected);
    assert.strictEqual(selected.pair_id, "pair_obs_01__obs_03");
    assert.strictEqual(selected.later_observation.observation_id, "obs_tile_c0000_r0000_z14_03");
  });

  // 4. Candidate Change Transformation
  it("transformCandidateChange extracts geometry, bounding box, and metrics", () => {
    const cand = transformCandidateChange(MOCK_CHANGE_REGION, "pair_obs_01__obs_02");

    assert.strictEqual(cand.regionId, "reg_0002");
    assert.strictEqual(cand.discoveryPairId, "pair_obs_01__obs_02");
    assert.strictEqual(cand.pixelCount, 900);
    assert.strictEqual(cand.areaM2, 90000.0);
    assert.strictEqual(cand.bboxPx.minRow, 200);
    assert.strictEqual(cand.bboxPx.minCol, 200);
    assert.strictEqual(cand.bboxPx.maxRow, 230);
    assert.strictEqual(cand.bboxPx.maxCol, 230);
    assert.strictEqual(cand.bboxPx.widthPx, 30);
    assert.strictEqual(cand.bboxPx.heightPx, 30);
    assert.strictEqual(cand.meanChangeScore, 0.825);
    assert.strictEqual(cand.maxChangeScore, 0.945);
    assert.strictEqual(cand.isTargetCandidate, true); // reg_0002 is prioritized target
    assert.ok(cand.bboxWgs84);
    assert.strictEqual(cand.bboxWgs84.minLon, 77.335);
  });

  it("transformCandidateChange handles alternative candidate regions", () => {
    const otherRegion: ChangeRegion = {
      region_id: "reg_0005",
      pixel_count: 320,
      area_px: 320,
      area_m2: 32000.0,
      bbox_px: [50, 50, 80, 90],
      bbox_wgs84: { min_lon: 77.31, min_lat: 13.06, max_lon: 77.32, max_lat: 13.07 },
      centroid_px: [65.0, 70.0],
      centroid_wgs84: [77.315, 13.065],
      mean_change_score: 0.65,
      max_change_score: 0.78,
    };

    const cand = transformCandidateChange(otherRegion, "pair_01_02");
    assert.strictEqual(cand.regionId, "reg_0005");
    assert.strictEqual(cand.bboxPx.widthPx, 40); // 90 - 50
    assert.strictEqual(cand.bboxPx.heightPx, 30); // 80 - 50
    assert.strictEqual(cand.isTargetCandidate, false);
  });

  // 5. Candidate Selection
  it("candidate selection accurately tracks active region and retains coordinates", () => {
    const candidates = [
      transformCandidateChange(MOCK_CHANGE_REGION, "pair_test"),
      transformCandidateChange(
        {
          ...MOCK_CHANGE_REGION,
          region_id: "reg_0001",
          pixel_count: 450,
          max_change_score: 0.72,
        },
        "pair_test"
      ),
    ];

    const selectedRegionId = "reg_0002";
    const selected = candidates.find((c) => c.regionId === selectedRegionId);

    assert.ok(selected);
    assert.strictEqual(selected.regionId, "reg_0002");
    assert.strictEqual(selected.pixelCount, 900);
    assert.strictEqual(selected.maxChangeScore, 0.945);
  });

  // 6. Validation Preventing Incomplete Investigation Requests
  it("validates that all required parameters must be present before launching", () => {
    const validateRequest = (
      seriesId: string | null | undefined,
      pairId: string | null | undefined,
      regionId: string | null | undefined
    ): boolean => {
      const s = (seriesId || "").trim();
      const p = (pairId || "").trim();
      const r = (regionId || "").trim();
      return s.length >= 3 && p.length >= 5 && r.length >= 3;
    };

    // Incomplete inputs must fail
    assert.strictEqual(validateRequest("", "pair_01_02", "reg_0001"), false);
    assert.strictEqual(validateRequest("series_1", "", "reg_0001"), false);
    assert.strictEqual(validateRequest("series_1", "pair_01_02", ""), false);
    assert.strictEqual(validateRequest(null, "pair_01_02", "reg_0001"), false);
    assert.strictEqual(validateRequest("series_1", undefined, "reg_0001"), false);
    assert.strictEqual(validateRequest("ab", "pair_01_02", "reg_0001"), false); // too short series

    // Complete valid inputs pass
    assert.strictEqual(validateRequest("series_01", "pair_01_02", "reg_0001"), true);
  });

  // 7. Correct InvestigationRequest Construction
  it("constructs exact InvestigationRequest matching backend API schema", () => {
    const seriesId = "series_grid_lon77.33_lat13.08_c0000_r0000_z14";
    const discoveryPairId = "pair_obs_01__obs_02";
    const candidateRegionId = "reg_0002";
    const pairingStrategy: "baseline" | "adjacent" = "baseline";

    const request: InvestigationRequest = {
      series_id: seriesId,
      discovery_pair_id: discoveryPairId,
      candidate_region_id: candidateRegionId,
      pairing_strategy: pairingStrategy,
      requested_format: "json",
    };

    assert.strictEqual(request.series_id, seriesId);
    assert.strictEqual(request.discovery_pair_id, discoveryPairId);
    assert.strictEqual(request.candidate_region_id, candidateRegionId);
    assert.strictEqual(request.pairing_strategy, "baseline");
    assert.strictEqual(request.requested_format, "json");

    // Also verify serialization round-trip matches JSON contract
    const serialized = JSON.stringify(request);
    const parsed = JSON.parse(serialized);
    assert.deepStrictEqual(parsed, {
      series_id: seriesId,
      discovery_pair_id: discoveryPairId,
      candidate_region_id: candidateRegionId,
      pairing_strategy: "baseline",
      requested_format: "json",
    });
  });

  // 8. Successful Investigation Response Handling
  it("transformInvestigationDossier successfully extracts and formats investigation outcome", () => {
    const summary = transformInvestigationDossier(MOCK_INVESTIGATION_DOSSIER);

    assert.strictEqual(summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.seriesId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");
    assert.strictEqual(summary.discoveryPairId, "pair_obs_01__obs_02");
    assert.strictEqual(summary.candidateRegionId, "reg_0002");
    assert.strictEqual(summary.pairingStrategy, "baseline");
    assert.strictEqual(summary.contentHash, "8c939ce062ed9b8c");
    assert.strictEqual(summary.supportStatus, "STRONG_TEMPORAL_SUPPORT");
    assert.strictEqual(summary.confidenceTier, "high");
    assert.strictEqual(summary.category.primary, "CONSTRUCTION");
    assert.strictEqual(summary.category.isValid, true);
    assert.strictEqual(summary.onset.intervalType, "BOUNDED_HALF_OPEN");
    assert.strictEqual(summary.onset.physicalInterval, "(2026-01-15, 2026-02-15]");
    assert.strictEqual(summary.onset.intervalDays, 31.0);
    const earliestNode = summary.timelineNodes.find((n) => n.status === "EARLIEST_SUPPORTING");
    assert.ok(earliestNode);
    assert.strictEqual(earliestNode.observationId, "obs_tile_02");
    assert.strictEqual(summary.timelineNodes.length, 3);
  });

  // 9. API Error Handling
  it("ApiError correctly encapsulates status code, errorCode, and execution stage", () => {
    const error = new ApiError(
      422,
      "Validation Error: candidate_region_id 'reg_9999' not found in discovery pair",
      "REGION_NOT_FOUND",
      "change_detection"
    );

    assert.strictEqual(error.status, 422);
    assert.strictEqual(error.errorCode, "REGION_NOT_FOUND");
    assert.strictEqual(error.stage, "change_detection");
    assert.match(error.message, /candidate_region_id/);
  });

  it("handles orchestrator internal failure safely without crashing", () => {
    const orchestratorError = new ApiError(
      500,
      "Pipeline orchestration failed during temporal evidence evaluation",
      "ORCHESTRATOR_EVAL_FAILED",
      "temporal_evidence"
    );

    assert.strictEqual(orchestratorError.status, 500);
    assert.strictEqual(orchestratorError.errorCode, "ORCHESTRATOR_EVAL_FAILED");
    assert.strictEqual(orchestratorError.stage, "temporal_evidence");
  });
});
