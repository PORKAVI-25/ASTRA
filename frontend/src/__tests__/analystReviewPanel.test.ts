/**
 * Unit Tests for AnalystReviewPanel Component & Business Logic
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  saveReviewRevision,
  getLatestReview,
  normalizeDecision,
  exportInvestigationReviewJson,
  clearAllReviews,
} from "../services/reviewStore.ts";
import { transformInvestigationDossier } from "../services/transformers.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationSummary } from "../types/models.ts";

// Mock LocalStorage
class MockLocalStorage {
  private store: Record<string, string> = {};
  getItem(key: string): string | null { return this.store[key] || null; }
  setItem(key: string, value: string): void { this.store[key] = value; }
  removeItem(key: string): void { delete this.store[key]; }
  clear(): void { this.store = {}; }
}

const mockStorage = new MockLocalStorage();
(globalThis as unknown as { window: { localStorage: MockLocalStorage } }).window = {
  localStorage: mockStorage,
};

describe("Milestone D9: AnalystReviewPanel Logic Unit Tests", () => {
  beforeEach(() => {
    mockStorage.clear();
    clearAllReviews();
  });

  it("extracts read-only machine assessment without modifying source data", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    // Read-only machine properties
    assert.strictEqual(summary.category.primary, "CONSTRUCTION");
    assert.strictEqual(summary.confidenceTier, "high");
    assert.strictEqual(summary.supportStatus, "STRONG_TEMPORAL_SUPPORT");

    // Ensure analyst review state defaults to unreviewed
    const latest = getLatestReview(summary.investigationId, summary.candidateRegionId);
    assert.strictEqual(latest, null);
  });

  it("enforces confirmation guard preventing accidental blank saves", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    const initialSave = saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "CONFIRMED",
      analystNote: "Confirmed physical excavation matching temporal step.",
      selectedReason: "True positive change confirmed",
    });
    assert.strictEqual(initialSave.created, true);

    // Attempt identical save: should trigger duplicate guard
    const duplicateSave = saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "CONFIRMED",
      analystNote: "Confirmed physical excavation matching temporal step.",
      selectedReason: "True positive change confirmed",
    });
    assert.strictEqual(duplicateSave.created, false);
    assert.strictEqual(duplicateSave.isDuplicate, true);
  });

  it("allows transition from CONFIRMED to REJECTED with mandatory note", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "CONFIRMED",
      analystNote: "Initial review.",
    });

    const rev2 = saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "REJECTED",
      analystNote: "Re-evaluated: false positive due to off-nadir parallax effect.",
      selectedReason: "False alarm / Sensor artifact or co-registration error",
    });

    assert.strictEqual(rev2.created, true);
    assert.strictEqual(rev2.revisionNumber, 2);
    assert.strictEqual(rev2.review.decision, "REJECTED");
    assert.strictEqual(rev2.review.previousDecision, "CONFIRMED");

    // Verify machine classification remains completely untouched
    assert.strictEqual(summary.category.primary, "CONSTRUCTION");
    assert.strictEqual(summary.confidenceTier, "high");
  });

  it("exports valid audit JSON containing both machine references and analyst history", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      seriesId: summary.seriesId,
      discoveryPairId: summary.discoveryPairId,
      decision: "CONFIRMED",
      analystNote: "Ready for reporting.",
      selectedReason: "True positive change confirmed",
    });

    const exportJson = exportInvestigationReviewJson(summary.investigationId, summary.candidateRegionId);
    const parsed = JSON.parse(exportJson);

    assert.strictEqual(parsed.schemaVersion, "astra_review_v2");
    assert.strictEqual(parsed.investigationId, summary.investigationId);
    assert.strictEqual(parsed.candidateRegionId, summary.candidateRegionId);
    assert.strictEqual(parsed.currentDecision, "CONFIRMED");
    assert.strictEqual(parsed.totalRevisions, 1);
    assert.match(parsed.currentAuditHash, /^[0-9a-f]{64}$/);
  });

  it("normalizes legacy decision values cleanly", () => {
    assert.strictEqual(normalizeDecision("CONFIRM"), "CONFIRMED");
    assert.strictEqual(normalizeDecision("REJECT"), "REJECTED");
    assert.strictEqual(normalizeDecision("FLAG_NEEDS_REVIEW"), "PENDING");
  });
});
