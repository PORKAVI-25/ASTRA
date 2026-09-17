/**
 * Unit Tests for Pure View-Model Transformers
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  formatDisplayDate,
  formatDisplayDateTime,
  getNodeStatusColor,
  transformCandidateChange,
  transformInvestigationDossier,
  transformScenePair,
  transformTemporalObservation,
  transformTemporalSeries,
  transformTimelineNode,
} from "../services/transformers.ts";

import {
  MOCK_CHANGE_REGION,
  MOCK_INVESTIGATION_DOSSIER,
  MOCK_SCENE_PAIR,
  MOCK_TEMPORAL_SERIES,
  MOCK_TIMELINE_NODES,
} from "./fixtures.ts";

describe("Transformers Service Unit Tests", () => {
  it("formatDisplayDate formats ISO date correctly", () => {
    const formatted = formatDisplayDate("2026-01-15T10:30:00Z");
    assert.match(formatted, /Jan 15, 2026/);
    assert.strictEqual(formatDisplayDate(""), "N/A");
  });

  it("formatDisplayDateTime formats ISO date and time", () => {
    const formatted = formatDisplayDateTime("2026-01-15T10:30:00Z");
    assert.match(formatted, /Jan 15, 2026/);
    assert.match(formatted, /UTC/);
  });

  it("getNodeStatusColor maps statuses to expected Tailwind tokens", () => {
    assert.strictEqual(getNodeStatusColor("EARLIEST_SUPPORTING"), "emerald");
    assert.strictEqual(getNodeStatusColor("PERSISTENT_SUPPORT"), "blue");
    assert.strictEqual(getNodeStatusColor("FLAGGED_SUPPORT"), "amber");
    assert.strictEqual(getNodeStatusColor("SUPPRESSED_ARTIFACT"), "rose");
    assert.strictEqual(getNodeStatusColor("PRE_CHANGE_ABSENCE"), "slate");
  });

  it("transformTemporalObservation extracts expected view model fields", () => {
    const raw = MOCK_TEMPORAL_SERIES.observations[0];
    const obs = transformTemporalObservation(raw);

    assert.strictEqual(obs.observationId, "obs_tile_c0000_r0000_z14_01");
    assert.strictEqual(obs.platform, "Sentinel-2A");
    assert.strictEqual(obs.sensor, "MSI");
    assert.strictEqual(obs.isSynthetic, true);
    assert.strictEqual(obs.cloudCoverPct, 0.0);
    assert.match(obs.displayDate, /Jan 15, 2026/);
  });

  it("transformTemporalSeries extracts series summary and aggregated sensors", () => {
    const summary = transformTemporalSeries(MOCK_TEMPORAL_SERIES);

    assert.strictEqual(summary.seriesId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");
    assert.strictEqual(summary.observationCount, 4);
    assert.strictEqual(summary.timespanDays, 90.0);
    assert.deepStrictEqual(summary.sensors, ["MSI"]);
    assert.strictEqual(summary.observations.length, 2);
  });

  it("transformScenePair maps pair metadata and compatibility", () => {
    const pair = transformScenePair(MOCK_SCENE_PAIR, "series_123");

    assert.strictEqual(pair.pairId, "pair_obs_01__obs_02");
    assert.strictEqual(pair.seriesId, "series_123");
    assert.strictEqual(pair.isCompatible, true);
    assert.strictEqual(pair.temporalBaselineDays, 31.0);
    assert.strictEqual(pair.earlierPlatform, "Sentinel-2A");
    assert.strictEqual(pair.laterPlatform, "Sentinel-2B");
  });

  it("transformCandidateChange extracts bounding box dimensions and coordinates", () => {
    const candidate = transformCandidateChange(MOCK_CHANGE_REGION, "pair_obs_01__obs_02");

    assert.strictEqual(candidate.regionId, "reg_0002");
    assert.strictEqual(candidate.discoveryPairId, "pair_obs_01__obs_02");
    assert.strictEqual(candidate.pixelCount, 900);
    assert.strictEqual(candidate.areaM2, 90000.0);
    assert.strictEqual(candidate.bboxPx.widthPx, 30);
    assert.strictEqual(candidate.bboxPx.heightPx, 30);
    assert.strictEqual(candidate.meanChangeScore, 0.825);
    assert.strictEqual(candidate.maxChangeScore, 0.945);
    assert.strictEqual(candidate.isTargetCandidate, true);
  });

  it("transformTimelineNode extracts spatial metrics and color tokens", () => {
    const node = transformTimelineNode(MOCK_TIMELINE_NODES[1]); // EARLIEST_SUPPORTING

    assert.strictEqual(node.observationId, "obs_tile_02");
    assert.strictEqual(node.status, "EARLIEST_SUPPORTING");
    assert.strictEqual(node.statusColor, "emerald");
    assert.strictEqual(node.m4dDecision, "RETAINED");
    assert.strictEqual(node.supportScore, 0.92);
    assert.strictEqual(node.isEarliestSupportEligible, true);
    assert.strictEqual(node.categoryObserved, "construction");
    assert.strictEqual(node.categoryConfidence, "high");
    assert.strictEqual(node.spatialAlignment.iouWgs84, 1.0);
    assert.strictEqual(node.spatialAlignment.centroidDistanceM, 0.0);
  });

  it("transformInvestigationDossier transforms complete dossier and tracks region ID shifts", () => {
    const summary = transformInvestigationDossier(MOCK_INVESTIGATION_DOSSIER);

    assert.strictEqual(summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.status, "COMPLETED");
    assert.strictEqual(summary.candidateRegionId, "reg_0002");
    assert.strictEqual(summary.contentHash, "8c939ce062ed9b8c");
    assert.strictEqual(summary.supportStatus, "STRONG_TEMPORAL_SUPPORT");
    assert.strictEqual(summary.confidenceTier, "high");

    // Onset interval
    assert.strictEqual(summary.onset.intervalType, "BOUNDED_HALF_OPEN");
    assert.strictEqual(summary.onset.displaySpan, "[2026-01-15, 2026-02-15]");
    assert.strictEqual(summary.onset.physicalInterval, "(2026-01-15, 2026-02-15]");
    assert.strictEqual(summary.onset.intervalDays, 31.0);

    // Category
    assert.strictEqual(summary.category.primary, "CONSTRUCTION");
    assert.strictEqual(summary.category.isValid, true);

    // Spatial Correspondence Tracking across epochs
    assert.strictEqual(summary.spatialCorrespondence.epochs.length, 2);
    const shiftEpoch = summary.spatialCorrespondence.epochs[1];
    assert.strictEqual(shiftEpoch.referenceCandidateId, "reg_0002");
    assert.strictEqual(shiftEpoch.matchedRegionId, "reg_0001");
    assert.strictEqual(shiftEpoch.isIdShifted, true);
    assert.strictEqual(shiftEpoch.metricIou, 0.88);
    assert.strictEqual(shiftEpoch.centroidDistanceM, 4.2);

    // Suppression
    assert.strictEqual(summary.suppression.overallScreeningOutcome, "PASS");
    assert.strictEqual(summary.suppression.totalEpochsRetained, 2);

    // Lineage & Provenance
    assert.strictEqual(summary.provenance.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.provenance.isVerified, true);
    assert.strictEqual(summary.provenance.stages.length, 2);
  });
});
