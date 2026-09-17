/**
 * Unit Tests for Milestone D5: Temporal Timeline
 *
 * Covers:
 * 1. Full four-epoch timeline renders.
 * 2. Chronological ordering is correct.
 * 3. PRE_CHANGE_ABSENCE is represented correctly.
 * 4. EARLIEST_SUPPORTING is represented correctly.
 * 5. PERSISTENT_SUPPORT is represented correctly.
 * 6. FLAGGED_SUPPORT / SUPPRESSED_ARTIFACT are handled.
 * 7. INSUFFICIENT_DATA is handled without crashing.
 * 8. Mathematical onset interval is displayed exactly as (T_pre, T_earliest].
 * 9. No exact event date is fabricated.
 * 10. Region ID correspondence across epochs is displayed without assuming IDs are stable.
 * 11. Missing optional fields do not crash rendering.
 * 12. D3 -> D4 -> D5 data handoff remains compatible.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  transformInvestigationDossier,
  sortTimelineNodesChronologically,
  getNodeStatusDetails,
  getM4dDecisionDetails,
  formatMathematicalOnset,
  matchNodeCorrespondence,
} from "../services/transformers.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationDossier, TemporalEvidenceNode } from "../types/api.ts";
import type { InvestigationSummary, TemporalTimelineNode } from "../types/models.ts";

describe("Milestone D5: Temporal Timeline Unit Tests", () => {
  // 1. Full four-epoch timeline renders
  it("renders full four-epoch timeline with correct counts and dates", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    assert.strictEqual(summary.timelineNodes.length, 4);

    const dates = summary.timelineNodes.map((n) => n.acquisitionTime.substring(0, 10));
    assert.deepStrictEqual(dates, [
      "2026-01-15",
      "2026-02-15",
      "2026-03-15",
      "2026-04-15",
    ]);

    // All nodes have valid status details
    for (const node of summary.timelineNodes) {
      const details = getNodeStatusDetails(node.status);
      assert.ok(details.label.length > 0);
      assert.ok(details.description.length > 0);
      assert.ok(details.icon.length > 0);
      assert.ok(details.badgeClasses.length > 0);
    }
  });

  // 2. Chronological ordering is strictly enforced
  it("enforces strict chronological ordering regardless of input sequence", () => {
    const unorderedNodes: TemporalTimelineNode[] = [
      {
        observationId: "obs_04",
        acquisitionTime: "2026-04-15T10:30:00Z",
        displayDate: "Apr 15, 2026",
        sensor: "MSI",
        platform: "Sentinel-2B",
        status: "PERSISTENT_SUPPORT",
        statusColor: "blue",
        m4dDecision: "RETAINED",
        supportScore: 0.89,
        isEarliestSupportEligible: false,
        spatialAlignment: { status: "OK", relationship: "MATCHED", isCompatible: true, iouWgs84: 0.85 },
        isCrossSensor: false,
        reasons: [],
        limitations: [],
      },
      {
        observationId: "obs_01",
        acquisitionTime: "2026-01-15T10:30:00Z",
        displayDate: "Jan 15, 2026",
        sensor: "MSI",
        platform: "Sentinel-2A",
        status: "PRE_CHANGE_ABSENCE",
        statusColor: "slate",
        m4dDecision: null,
        supportScore: 0.0,
        isEarliestSupportEligible: false,
        spatialAlignment: { status: "OK", relationship: "MATCHED", isCompatible: true, iouWgs84: 1.0 },
        isCrossSensor: false,
        reasons: [],
        limitations: [],
      },
      {
        observationId: "obs_03",
        acquisitionTime: "2026-03-15T10:30:00Z",
        displayDate: "Mar 15, 2026",
        sensor: "MSI",
        platform: "Sentinel-2A",
        status: "PERSISTENT_SUPPORT",
        statusColor: "blue",
        m4dDecision: "RETAINED",
        supportScore: 0.92,
        isEarliestSupportEligible: false,
        spatialAlignment: { status: "OK", relationship: "MATCHED", isCompatible: true, iouWgs84: 0.88 },
        isCrossSensor: false,
        reasons: [],
        limitations: [],
      },
      {
        observationId: "obs_02",
        acquisitionTime: "2026-02-15T10:30:00Z",
        displayDate: "Feb 15, 2026",
        sensor: "MSI",
        platform: "Sentinel-2B",
        status: "EARLIEST_SUPPORTING",
        statusColor: "emerald",
        m4dDecision: "RETAINED",
        supportScore: 0.96,
        isEarliestSupportEligible: true,
        spatialAlignment: { status: "OK", relationship: "MATCHED", isCompatible: true, iouWgs84: 1.0 },
        isCrossSensor: false,
        reasons: [],
        limitations: [],
      },
    ];

    const sorted = sortTimelineNodesChronologically(unorderedNodes);
    assert.strictEqual(sorted[0].observationId, "obs_01");
    assert.strictEqual(sorted[1].observationId, "obs_02");
    assert.strictEqual(sorted[2].observationId, "obs_03");
    assert.strictEqual(sorted[3].observationId, "obs_04");

    // Check timestamps are strictly monotonically increasing
    for (let i = 1; i < sorted.length; i++) {
      const prev = new Date(sorted[i - 1].acquisitionTime).getTime();
      const curr = new Date(sorted[i].acquisitionTime).getTime();
      assert.ok(curr > prev, `Expected node ${i} to be later than node ${i - 1}`);
    }
  });

  // 3. PRE_CHANGE_ABSENCE representation
  it("represents PRE_CHANGE_ABSENCE correctly as baseline absence without fabricating support", () => {
    const details = getNodeStatusDetails("PRE_CHANGE_ABSENCE");

    assert.strictEqual(details.status, "PRE_CHANGE_ABSENCE");
    assert.strictEqual(details.label, "Pre-Change Absence");
    assert.strictEqual(details.colorToken, "slate");
    assert.match(details.description, /absence/i);
    assert.match(details.description, /pre-change/i);

    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const preNode = summary.timelineNodes[0];

    assert.strictEqual(preNode.status, "PRE_CHANGE_ABSENCE");
    assert.strictEqual(preNode.supportScore, 0.0);
    assert.strictEqual(preNode.isEarliestSupportEligible, false);
  });

  // 4. EARLIEST_SUPPORTING representation
  it("represents EARLIEST_SUPPORTING correctly with earliest eligibility", () => {
    const details = getNodeStatusDetails("EARLIEST_SUPPORTING");

    assert.strictEqual(details.status, "EARLIEST_SUPPORTING");
    assert.strictEqual(details.label, "Earliest Supporting");
    assert.strictEqual(details.colorToken, "emerald");
    assert.match(details.description, /earliest/i);

    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const earliestNode = summary.timelineNodes[1];

    assert.strictEqual(earliestNode.status, "EARLIEST_SUPPORTING");
    assert.strictEqual(earliestNode.isEarliestSupportEligible, true);
    assert.ok(earliestNode.supportScore >= 0.9);
  });

  // 5. PERSISTENT_SUPPORT representation
  it("represents PERSISTENT_SUPPORT correctly across subsequent observation epochs", () => {
    const details = getNodeStatusDetails("PERSISTENT_SUPPORT");

    assert.strictEqual(details.status, "PERSISTENT_SUPPORT");
    assert.strictEqual(details.label, "Persistent Support");
    assert.strictEqual(details.colorToken, "blue");
    assert.match(details.description, /persistent/i);

    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const node3 = summary.timelineNodes[2];
    const node4 = summary.timelineNodes[3];

    assert.strictEqual(node3.status, "PERSISTENT_SUPPORT");
    assert.strictEqual(node4.status, "PERSISTENT_SUPPORT");
    assert.strictEqual(node3.isEarliestSupportEligible, false);
    assert.strictEqual(node4.isEarliestSupportEligible, false);
  });

  // 6. FLAGGED_SUPPORT and SUPPRESSED_ARTIFACT handling
  it("distinguishes FLAGGED_SUPPORT and SUPPRESSED_ARTIFACT with M4D false-alarm screening", () => {
    // FLAGGED_SUPPORT
    const flaggedDetails = getNodeStatusDetails("FLAGGED_SUPPORT");
    assert.strictEqual(flaggedDetails.status, "FLAGGED_SUPPORT");
    assert.strictEqual(flaggedDetails.label, "Flagged Support");
    assert.strictEqual(flaggedDetails.colorToken, "amber");
    assert.strictEqual(flaggedDetails.icon, "⚠️");
    assert.match(flaggedDetails.description, /risk/i);

    // SUPPRESSED_ARTIFACT
    const suppressedDetails = getNodeStatusDetails("SUPPRESSED_ARTIFACT");
    assert.strictEqual(suppressedDetails.status, "SUPPRESSED_ARTIFACT");
    assert.strictEqual(suppressedDetails.label, "Suppressed Artifact");
    assert.strictEqual(suppressedDetails.colorToken, "rose");
    assert.strictEqual(suppressedDetails.icon, "🚫");
    assert.match(suppressedDetails.description, /suppressed/i);

    // M4D Decision Details
    const m4dRetained = getM4dDecisionDetails("RETAINED");
    assert.strictEqual(m4dRetained.decision, "RETAINED");
    assert.match(m4dRetained.label, /Pass/i);

    const m4dFlagged = getM4dDecisionDetails("FLAGGED");
    assert.strictEqual(m4dFlagged.decision, "FLAGGED");
    assert.match(m4dFlagged.label, /Risk/i);

    const m4dSuppressed = getM4dDecisionDetails("SUPPRESSED");
    assert.strictEqual(m4dSuppressed.decision, "SUPPRESSED");
    assert.match(m4dSuppressed.label, /Artifact/i);
  });

  // 7. INSUFFICIENT_DATA and SIMULTANEOUS_CO_TEMPORAL handling
  it("handles INSUFFICIENT_DATA and SIMULTANEOUS_CO_TEMPORAL without crashing", () => {
    const insufficientDetails = getNodeStatusDetails("INSUFFICIENT_DATA");
    assert.strictEqual(insufficientDetails.status, "INSUFFICIENT_DATA");
    assert.strictEqual(insufficientDetails.label, "Insufficient Data");
    assert.strictEqual(insufficientDetails.icon, "❓");
    assert.match(insufficientDetails.description, /occlusion|cloud|missing/i);

    const simultaneousDetails = getNodeStatusDetails("SIMULTANEOUS_CO_TEMPORAL");
    assert.strictEqual(simultaneousDetails.status, "SIMULTANEOUS_CO_TEMPORAL");
    assert.strictEqual(simultaneousDetails.label, "Simultaneous Co-Temporal");
    assert.strictEqual(simultaneousDetails.colorToken, "purple");

    // Dossier with INSUFFICIENT_DATA node
    const sparseNode: TemporalEvidenceNode = {
      observation_id: "obs_cloudy_01",
      acquisition_time: "2026-05-15T10:30:00Z",
      sensor: "MSI",
      platform: "Sentinel-2A",
      node_status: "INSUFFICIENT_DATA",
      heuristic_support_score: 0.1,
      eligible_for_earliest_support: false,
      spatial_correspondence: {
        status: "OCCLUDED",
        relationship: "NONE",
        is_spatially_compatible: false,
        iou_wgs84: 0.0,
        crs_match: true,
        gsd_match: true,
      },
      is_cross_sensor: false,
      decision_reasons: ["Heavy cloud cover exceeds 85% threshold."],
      data_limitations: ["Candidate region fully obscured by cloud shadow."],
    };

    const sparseDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      temporal_evidence: {
        ...DEMO_INVESTIGATION_DOSSIER.temporal_evidence!,
        timeline_nodes: [sparseNode],
      },
    };

    const summary = transformInvestigationDossier(sparseDossier);
    assert.strictEqual(summary.timelineNodes.length, 1);
    assert.strictEqual(summary.timelineNodes[0].status, "INSUFFICIENT_DATA");
  });

  // 8. Mathematical onset interval displayed exactly as (T_pre, T_earliest]
  it("formats mathematical onset bounding interval strictly as (T_pre, T_earliest]", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const onsetDetails = formatMathematicalOnset(
      summary.onset.preChangeDate,
      summary.onset.earliestSupportDate,
      summary.onset.preChangeObservationId,
      summary.onset.earliestSupportObservationId,
      summary.onset.intervalDays,
      summary.onset.intervalType
    );

    // Formula definition
    assert.strictEqual(onsetDetails.formula, "(T_pre, T_earliest]");
    assert.strictEqual(onsetDetails.intervalType, "BOUNDED_HALF_OPEN");

    // Concrete physical interval in demo
    assert.strictEqual(summary.onset.physicalInterval, "(2026-01-15, 2026-02-15]");
    assert.strictEqual(onsetDetails.intervalDays, 31.0);

    // Explanations
    assert.strictEqual(
      onsetDetails.tPreExplanation,
      "T_pre is the latest observation supporting absence/pre-change evidence."
    );
    assert.strictEqual(
      onsetDetails.tEarliestExplanation,
      "T_earliest is the earliest observation supporting the detected change."
    );
  });

  // 9. No exact event date is fabricated
  it("enforces that no exact event date is fabricated from discrete satellite passes", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const onsetDetails = formatMathematicalOnset(
      summary.onset.preChangeDate,
      summary.onset.earliestSupportDate,
      summary.onset.preChangeObservationId,
      summary.onset.earliestSupportObservationId,
      summary.onset.intervalDays
    );

    assert.match(
      onsetDetails.eventTimeExplanation,
      /actual event time is not known exactly from discrete satellite observations/i
    );
    assert.match(
      onsetDetails.noDateFabricationNotice,
      /no exact event date is fabricated/i
    );

    // Verify summary.onset does not have any fabricated exact "event_date" or "change_date"
    assert.strictEqual((summary.onset as any).exactEventDate, undefined);
    assert.strictEqual((summary.onset as any).eventDate, undefined);
    assert.strictEqual((summary.onset as any).changeDate, undefined);
  });

  // 10. Region ID correspondence across epochs without assuming stable IDs
  it("displays region ID correspondence across epochs without assuming stable local IDs", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const epochs = summary.spatialCorrespondence.epochs;

    assert.strictEqual(epochs.length, 3);

    // Epoch 1 (T1 -> T2): Discovery candidate reference reg_0002
    const match1 = matchNodeCorrespondence(
      summary.timelineNodes[1],
      1,
      epochs,
      summary.candidateRegionId
    );
    assert.strictEqual(match1.referenceCandidateId, "reg_0002");
    assert.strictEqual(match1.matchedRegionId, "reg_0002");
    assert.strictEqual(match1.isIdShifted, false);
    assert.strictEqual(match1.metricIou, 1.0);
    assert.strictEqual(match1.centroidDistanceM, 0.0);

    // Epoch 2 (T1 -> T3): Local region ID shift: reg_0002 -> reg_0001
    const match2 = matchNodeCorrespondence(
      summary.timelineNodes[2],
      2,
      epochs,
      summary.candidateRegionId
    );
    assert.strictEqual(match2.referenceCandidateId, "reg_0002");
    assert.strictEqual(match2.matchedRegionId, "reg_0001");
    assert.strictEqual(match2.isIdShifted, true);
    assert.strictEqual(match2.shiftDisplay, "reg_0002 → reg_0001");
    assert.strictEqual(match2.metricIou, 0.88);
    assert.strictEqual(match2.centroidDistanceM, 4.2);

    // Epoch 3 (T1 -> T4): Local region ID shift: reg_0002 -> reg_0003
    const match3 = matchNodeCorrespondence(
      summary.timelineNodes[3],
      3,
      epochs,
      summary.candidateRegionId
    );
    assert.strictEqual(match3.referenceCandidateId, "reg_0002");
    assert.strictEqual(match3.matchedRegionId, "reg_0003");
    assert.strictEqual(match3.isIdShifted, true);
    assert.strictEqual(match3.shiftDisplay, "reg_0002 → reg_0003");
    assert.strictEqual(match3.metricIou, 0.85);
    assert.strictEqual(match3.centroidDistanceM, 4.8);
  });

  // 11. Missing optional fields do not crash rendering
  it("safely handles incomplete or missing timeline and onset fields without crashing", () => {
    // Empty timeline
    const emptyOnset = formatMathematicalOnset(undefined, undefined);
    assert.strictEqual(emptyOnset.isBounded, false);
    assert.strictEqual(emptyOnset.formattedInterval, "(T_pre, T_earliest]");
    assert.strictEqual(emptyOnset.intervalDays, 0);

    // Missing correspondence
    const singleNode: TemporalTimelineNode = {
      observationId: "obs_single_01",
      acquisitionTime: "",
      displayDate: "N/A",
      sensor: "",
      platform: "",
      status: "NO_SUPPORT",
      statusColor: "slate",
      m4dDecision: null,
      supportScore: 0,
      isEarliestSupportEligible: false,
      spatialAlignment: { status: "UNKNOWN", relationship: "NONE", isCompatible: false, iouWgs84: 0 },
      isCrossSensor: false,
      reasons: [],
      limitations: [],
    };

    const emptyMatch = matchNodeCorrespondence(singleNode, 0, [], "reg_default");
    assert.strictEqual(emptyMatch.referenceCandidateId, "reg_default");
    assert.strictEqual(emptyMatch.isIdShifted, false);

    // Missing M4D decision
    const m4dEmpty = getM4dDecisionDetails(null);
    assert.strictEqual(m4dEmpty.decision, "NOT_EVALUATED");

    // Node status fallback
    const unknownStatus = getNodeStatusDetails("COMPLETELY_UNKNOWN_STATUS");
    assert.strictEqual(unknownStatus.label, "No Support");
  });

  // 12. D3 -> D4 -> D5 data handoff compatibility
  it("preserves data lineage and pipeline artifacts from D3/D4 through D5 timeline", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    // D3 inputs preserved
    assert.strictEqual(summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.seriesId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");
    assert.strictEqual(summary.discoveryPairId, "pair_obs_01__obs_02");
    assert.strictEqual(summary.candidateRegionId, "reg_0002");

    // D4 executive summary fields intact
    assert.strictEqual(summary.category.primary, "CONSTRUCTION");
    assert.strictEqual(summary.supportStatus, "STRONG_TEMPORAL_SUPPORT");
    assert.strictEqual(summary.confidenceTier, "high");

    // D5 timeline fields populated and ready for visualization
    assert.strictEqual(summary.timelineNodes.length, 4);
    assert.strictEqual(summary.timelineNodes[0].status, "PRE_CHANGE_ABSENCE");
    assert.strictEqual(summary.timelineNodes[1].status, "EARLIEST_SUPPORTING");
    assert.strictEqual(summary.timelineNodes[2].status, "PERSISTENT_SUPPORT");
    assert.strictEqual(summary.timelineNodes[3].status, "PERSISTENT_SUPPORT");

    // Spatial correspondence handoff
    assert.strictEqual(summary.spatialCorrespondence.epochs.length, 3);
    assert.strictEqual(summary.spatialCorrespondence.referenceCandidateId, "reg_0002");
  });
});
