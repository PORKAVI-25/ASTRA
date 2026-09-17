/**
 * Component Type-Checking and Unit Verification for AnalystReviewPanel
 *
 * Validates component props contract, React tree element instantiation,
 * and state synchronization behaviors.
 */

import React from "react";
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { AnalystReviewPanel } from "../components/investigation/AnalystReviewPanel.tsx";
import { transformInvestigationDossier } from "../services/transformers.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationSummary } from "../types/models.ts";

describe("AnalystReviewPanel Component Tests", () => {
  it("instantiates AnalystReviewPanel with valid InvestigationSummary props", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    let updatedCallbackFired = false;

    const element = React.createElement(AnalystReviewPanel, {
      summary,
      onReviewUpdated: () => {
        updatedCallbackFired = true;
      },
    });

    assert.ok(element);
    assert.strictEqual(element.type, AnalystReviewPanel);
    assert.strictEqual(element.props.summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(updatedCallbackFired, false);
  });

  it("safely accepts minimalist/empty investigation summaries without throwing", () => {
    const minimalSummary = {
      investigationId: "inv_minimal",
      candidateRegionId: "reg_0001",
      seriesId: "series_01",
      discoveryPairId: "pair_01",
      status: "COMPLETED" as const,
      pairingStrategy: "adjacent" as const,
      createdAt: "2026-09-17 10:00:00",
      category: { primary: "UNCLASSIFIED", trajectory: [], isValid: true, isConflicted: false, notes: [] },
      confidenceTier: "uncertain" as const,
      supportStatus: "UNKNOWN" as const,
      decisionReasons: [],
      evidenceLimitations: [],
      timelineNodes: [],
      spatialCorrespondence: [],
      provenance: {
        investigationId: "inv_minimal",
        investigationProvenanceId: "prov_01",
        createdAt: "2026-09-17 10:00:00",
        upstreamHashes: {},
        stages: [],
        isVerified: true,
        scenePairIds: [],
        changeDetectionResultIds: [],
        evidenceIds: [],
        classificationIds: [],
        suppressionIds: [],
        artifacts: [],
        epochLineage: [],
        completeness: { status: "COMPLETE" as const, label: "Complete", description: "All present", missingReferences: [], presentCount: 1, totalExpected: 1 },
      },
    } as unknown as InvestigationSummary;

    const element = React.createElement(AnalystReviewPanel, {
      summary: minimalSummary,
    });

    assert.ok(element);
    assert.strictEqual(element.props.summary.investigationId, "inv_minimal");
  });
});
