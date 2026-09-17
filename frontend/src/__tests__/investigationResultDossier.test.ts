/**
 * Unit Tests for Milestone D4: Investigation Result Dossier
 *
 * Covers:
 * - dossier transformation
 * - executive summary extraction
 * - onset interval formatting
 * - stage status extraction
 * - caveat handling
 * - lineage extraction
 * - insufficient/ambiguous result handling
 * - successful D3 -> D4 dossier handoff
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { transformInvestigationDossier } from "../services/transformers.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationDossier } from "../types/api.ts";
import type { InvestigationSummary } from "../types/models.ts";

describe("Milestone D4: Investigation Result Dossier Unit Tests", () => {
  // 1. Dossier Transformation
  it("transformInvestigationDossier transforms full multi-epoch investigation dossier", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(
      DEMO_INVESTIGATION_DOSSIER
    );

    assert.strictEqual(summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.status, "COMPLETED");
    assert.strictEqual(summary.seriesId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");
    assert.strictEqual(summary.discoveryPairId, "pair_obs_01__obs_02");
    assert.strictEqual(summary.candidateRegionId, "reg_0002");
    assert.strictEqual(summary.contentHash, "8c939ce062ed9b8c");
    assert.strictEqual(summary.provenance.isVerified, true);
  });

  // 2. Executive Summary Extraction
  it("extracts primary executive assessment fields accurately", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    // Primary Category & Validation
    assert.strictEqual(summary.category.primary, "CONSTRUCTION");
    assert.strictEqual(summary.category.isValid, true);
    assert.deepStrictEqual(summary.category.trajectory, ["construction", "construction"]);

    // Temporal Support Status
    assert.strictEqual(summary.supportStatus, "STRONG_TEMPORAL_SUPPORT");

    // Confidence Tier
    assert.strictEqual(summary.confidenceTier, "high");

    // Evidentiary persistence metrics
    const supportingNodes = summary.timelineNodes.filter(
      (n) => n.status === "EARLIEST_SUPPORTING" || n.status === "PERSISTENT_SUPPORT"
    );
    assert.strictEqual(supportingNodes.length, 3);
    assert.strictEqual(summary.timelineNodes.length, 4);
  });

  // 3. Onset Interval Formatting
  it("formats mathematical onset bounding interval (T_pre, T_earliest] without fabricating exact dates", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const onset = summary.onset;

    assert.strictEqual(onset.intervalType, "BOUNDED_HALF_OPEN");
    assert.strictEqual(onset.physicalInterval, "(2026-01-15, 2026-02-15]");
    assert.strictEqual(onset.displaySpan, "[2026-01-15, 2026-02-15]");
    assert.strictEqual(onset.intervalDays, 31.0);

    // Bounding observation identifiers
    assert.strictEqual(onset.preChangeObservationId, "obs_tile_c0000_r0000_z14_01");
    assert.strictEqual(onset.earliestSupportObservationId, "obs_tile_c0000_r0000_z14_02");
    assert.match(onset.preChangeDate || "", /Jan 15, 2026/);
    assert.match(onset.earliestSupportDate || "", /Feb 15, 2026/);

    // Sampling limitation reminder preserved
    assert.match(onset.limitationNotice, /discrete satellite sampling bounds/);
  });

  // 4. Stage Status Extraction
  it("extracts all executed pipeline stages and outputs in chronological sequence", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const stages = summary.provenance.stages;

    assert.strictEqual(stages.length, 6);

    const stageNames = stages.map((s) => s.stage);
    assert.deepStrictEqual(stageNames, [
      "series_resolution",
      "m4b_change_detection",
      "m4c_evidence_extraction",
      "m4c_classification",
      "m4d_suppression",
      "m4e_temporal_evidence",
    ]);

    // Verify each stage completed
    for (const st of stages) {
      assert.strictEqual(st.status, "COMPLETED");
    }

    // Verify stage details preserved
    assert.strictEqual(stages[0].details.observation_count, 4);
    assert.strictEqual(stages[1].details.number_of_regions, 3);
    assert.strictEqual(stages[3].details.primary_category, "construction");
    assert.strictEqual(stages[4].details.outcome, "PASS");
  });

  // 5. Caveat Handling
  it("preserves audit justifications and acquisition limitations verbatim", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    assert.strictEqual(summary.decisionReasons.length, 2);
    assert.match(summary.decisionReasons[0], /Earliest supporting observation/);
    assert.match(summary.decisionReasons[1], /Persistent support confirmed/);

    assert.strictEqual(summary.evidenceLimitations.length, 1);
    assert.match(summary.evidenceLimitations[0], /discrete satellite sampling bounds/);
  });

  // 6. Lineage & Spatial Correspondence Tracking
  it("extracts upstream artifact hashes and tracks candidate correspondence region ID shifts", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const lineage = summary.provenance;
    const corr = summary.spatialCorrespondence;

    // Upstream SHA-256 hashes
    const tileHash = lineage.upstreamHashes["data/processed/tiles/obs_01.tif"];
    assert.strictEqual(tileHash, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");

    // Candidate Spatial Correspondence
    assert.strictEqual(corr.referenceCandidateId, "reg_0002");
    assert.strictEqual(corr.epochs.length, 3);

    // Epoch 1: T1 -> T2 exact discovery candidate
    const epoch1 = corr.epochs[0];
    assert.strictEqual(epoch1.referenceCandidateId, "reg_0002");
    assert.strictEqual(epoch1.matchedRegionId, "reg_0002");
    assert.strictEqual(epoch1.isIdShifted, false);
    assert.strictEqual(epoch1.metricIou, 1.0);

    // Epoch 2: T1 -> T3 local region ID shift: reg_0002 -> reg_0001
    const epoch2 = corr.epochs[1];
    assert.strictEqual(epoch2.referenceCandidateId, "reg_0002");
    assert.strictEqual(epoch2.matchedRegionId, "reg_0001");
    assert.strictEqual(epoch2.isIdShifted, true);
    assert.strictEqual(epoch2.metricIou, 0.88);
    assert.strictEqual(epoch2.centroidDistanceM, 4.2);

    // Epoch 3: T1 -> T4 local region ID shift: reg_0002 -> reg_0003
    const epoch3 = corr.epochs[2];
    assert.strictEqual(epoch3.referenceCandidateId, "reg_0002");
    assert.strictEqual(epoch3.matchedRegionId, "reg_0003");
    assert.strictEqual(epoch3.isIdShifted, true);
    assert.strictEqual(epoch3.metricIou, 0.85);
    assert.strictEqual(epoch3.centroidDistanceM, 4.8);
  });

  // 7. Insufficient / Ambiguous Result Handling
  it("handles ambiguous or unconfirmed temporal evidence without assuming high confidence", () => {
    const ambiguousDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      investigation_id: "inv_ambiguous_sample",
      content_hash: "hash_ambiguous",
      status: "COMPLETED",
      temporal_evidence: {
        ...DEMO_INVESTIGATION_DOSSIER.temporal_evidence!,
        temporal_support_status: "AMBIGUOUS_EVIDENCE",
        confidence_tier: "uncertain",
        onset_estimate: {
          interval_type: "UNRESOLVED_GAP",
          physical_onset_interval: "(T_pre, T_ambiguous]",
          display_bounding_span: "[T1, T3]",
          interval_days: 60.0,
          interval_limitation: "Large cloud data gap between observations.",
        },
        category_evolution: {
          primary_category: "unclassified",
          is_evolution_valid: false,
          is_conflicted: true,
          evolution_trajectory: ["unclassified", "vegetation"],
          audit_notes: ["Conflicting spectral signatures between epochs."],
        },
        decision_reasons: ["Persistent support threshold not met."],
        evidence_limitations: ["High cloud fraction in epoch T2."],
      },
    };

    const summary = transformInvestigationDossier(ambiguousDossier);

    assert.strictEqual(summary.investigationId, "inv_ambiguous_sample");
    assert.strictEqual(summary.supportStatus, "AMBIGUOUS_EVIDENCE");
    assert.strictEqual(summary.confidenceTier, "uncertain");
    assert.strictEqual(summary.category.primary, "UNCLASSIFIED");
    assert.strictEqual(summary.category.isValid, false);
    assert.strictEqual(summary.category.isConflicted, true);
    assert.strictEqual(summary.onset.intervalType, "UNRESOLVED_GAP");
    assert.strictEqual(summary.onset.intervalDays, 60.0);
    assert.strictEqual(summary.decisionReasons[0], "Persistent support threshold not met.");
  });

  it("handles sparse or missing optional fields gracefully without runtime exceptions", () => {
    const minimalDossier: InvestigationDossier = {
      investigation_id: "inv_minimal",
      request: {
        series_id: "series_min",
        discovery_pair_id: "pair_01_02",
        candidate_region_id: "reg_0001",
      },
      series_id: "series_min",
      discovery_pair_id: "pair_01_02",
      candidate_region_id: "reg_0001",
      stage_results: [],
      lineage: {
        scene_pair_ids: ["pair_01_02"],
        change_detection_result_ids: [],
        evidence_ids: [],
        classification_ids: [],
        suppression_ids: [],
        upstream_hashes: {},
        candidate_correspondence: {},
      },
      provenance_id: "prov_minimal",
      created_at: "2026-01-01T00:00:00Z",
      content_hash: "hash_minimal",
      temporal_evidence: null,
      status: "COMPLETED",
    };

    const summary = transformInvestigationDossier(minimalDossier);

    assert.strictEqual(summary.investigationId, "inv_minimal");
    assert.strictEqual(summary.supportStatus, "UNKNOWN");
    assert.strictEqual(summary.confidenceTier, "uncertain");
    assert.strictEqual(summary.timelineNodes.length, 0);
    assert.strictEqual(summary.spatialCorrespondence.epochs.length, 0);
    assert.strictEqual(summary.provenance.stages.length, 0);
  });

  // 8. Successful D3 -> D4 Dossier Handoff
  it("successfully ingests output from InvestigationLauncher directly into DossierView summary", () => {
    // Simulate what InvestigationLauncher returns on POST /api/v1/pipeline/investigate
    const launcherOutputDossier: InvestigationDossier = DEMO_INVESTIGATION_DOSSIER;

    // D3 passes raw InvestigationDossier to onInvestigationComplete callback
    const summary = transformInvestigationDossier(launcherOutputDossier);

    // DossierView consumes the transformed summary immediately
    assert.ok(summary);
    assert.strictEqual(summary.investigationId, launcherOutputDossier.investigation_id);
    assert.strictEqual(summary.seriesId, launcherOutputDossier.series_id);
    assert.strictEqual(summary.discoveryPairId, launcherOutputDossier.discovery_pair_id);
    assert.strictEqual(summary.candidateRegionId, launcherOutputDossier.candidate_region_id);
    assert.strictEqual(summary.provenance.stages.length, launcherOutputDossier.stage_results.length);
  });
});
