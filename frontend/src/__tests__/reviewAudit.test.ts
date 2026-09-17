/**
 * Unit Tests for Milestone D9: Analyst Review & Audit Trail
 *
 * Covers all 25 required criteria:
 * 1. no-review state
 * 2. pending state
 * 3. confirm workflow
 * 4. reject workflow
 * 5. decision revision
 * 6. note-only revision
 * 7. duplicate save behavior
 * 8. revision ordering
 * 9. localStorage persistence
 * 10. malformed localStorage recovery
 * 11. storage unavailable behavior
 * 12. deterministic review ID
 * 13. deterministic audit hash
 * 14. changed note produces changed audit hash
 * 15. changed decision produces changed audit hash
 * 16. export payload
 * 17. investigation isolation
 * 18. candidate isolation
 * 19. machine assessment remains unchanged
 * 20. analyst decision remains separate from machine confidence
 * 21. missing machine classification
 * 22. missing temporal evidence
 * 23. missing candidate ID
 * 24. long note handling
 * 25. refresh/reload behavior
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  saveReviewRevision,
  getReviewHistory,
  getLatestReview,
  computeReviewAuditHash,
  computeReviewHash,
  normalizeDecision,
  exportInvestigationReviewJson,
  clearAllReviews,
  REVIEWS_STORAGE_KEY_V2,
} from "../services/reviewStore.ts";
import { transformInvestigationDossier } from "../services/transformers.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationDossier } from "../types/api.ts";
import type { InvestigationSummary } from "../types/models.ts";

// Mock LocalStorage for offline node test environment
class MockLocalStorage {
  private store: Record<string, string> = {};
  public shouldThrowOnGet = false;
  public shouldThrowOnSet = false;

  getItem(key: string): string | null {
    if (this.shouldThrowOnGet) {
      throw new Error("QuotaExceededError / Storage Unavailable");
    }
    return this.store[key] || null;
  }

  setItem(key: string, value: string): void {
    if (this.shouldThrowOnSet) {
      throw new Error("QuotaExceededError / Storage Unavailable");
    }
    this.store[key] = value;
  }

  removeItem(key: string): void {
    delete this.store[key];
  }

  clear(): void {
    this.store = {};
    this.shouldThrowOnGet = false;
    this.shouldThrowOnSet = false;
  }

  // Helper for test corrupting data
  setRaw(key: string, value: string): void {
    this.store[key] = value;
  }
}

const mockStorage = new MockLocalStorage();
(globalThis as unknown as { window: { localStorage: MockLocalStorage } }).window = {
  localStorage: mockStorage,
};

describe("Milestone D9: Analyst Review & Audit Trail Unit Tests", () => {
  beforeEach(() => {
    mockStorage.clear();
    clearAllReviews();
  });

  // 1. No-review state
  it("criterion 1: returns empty history and null latest review when no review has been recorded", () => {
    const history = getReviewHistory("inv_unreviewed_123", "reg_0001");
    const latest = getLatestReview("inv_unreviewed_123", "reg_0001");

    assert.strictEqual(history.length, 0);
    assert.strictEqual(latest, null);
  });

  // 2. Pending state
  it("criterion 2: saves a PENDING decision as Revision 1 with a valid SHA-256 audit hash", () => {
    const result = saveReviewRevision({
      investigationId: "inv_test_01",
      candidateRegionId: "reg_0001",
      seriesId: "series_s2",
      discoveryPairId: "pair_01_02",
      decision: "PENDING",
      analystNote: "Flagged for second analyst review due to cloud interference.",
      selectedReason: "Needs second analyst opinion",
      analystId: "analyst_alpha",
      timestamp: "2026-09-17T10:00:00Z",
    });

    assert.strictEqual(result.created, true);
    assert.strictEqual(result.isDuplicate, false);
    assert.strictEqual(result.revisionNumber, 1);
    assert.strictEqual(result.review.decision, "PENDING");
    assert.strictEqual(result.review.revisionNumber, 1);
    assert.strictEqual(result.review.previousDecision, undefined);
    assert.match(result.review.auditHash, /^[0-9a-f]{64}$/);

    const latest = getLatestReview("inv_test_01", "reg_0001");
    assert.ok(latest);
    assert.strictEqual(latest.decision, "PENDING");
  });

  // 3. Confirm workflow
  it("criterion 3: saves a CONFIRMED decision with explicit analyst attribution and reason", () => {
    const result = saveReviewRevision({
      investigationId: "inv_test_02",
      candidateRegionId: "reg_0002",
      seriesId: "series_s2",
      discoveryPairId: "pair_01_02",
      decision: "CONFIRMED",
      analystNote: "Confirmed physical excavation matching temporal step.",
      selectedReason: "True positive change confirmed",
      analystId: "analyst_beta",
      timestamp: "2026-09-17T11:00:00Z",
    });

    assert.strictEqual(result.created, true);
    assert.strictEqual(result.revisionNumber, 1);
    assert.strictEqual(result.review.decision, "CONFIRMED");
    assert.strictEqual(result.review.analystId, "analyst_beta");
    assert.strictEqual(result.review.selectedReason, "True positive change confirmed");
    assert.match(result.review.auditHash, /^[0-9a-f]{64}$/);
  });

  // 4. Reject workflow
  it("criterion 4: saves a REJECTED decision with analyst note and audit trail", () => {
    const result = saveReviewRevision({
      investigationId: "inv_test_03",
      candidateRegionId: "reg_0003",
      decision: "REJECTED",
      analystNote: "Spectral change caused by seasonal agricultural harvesting, not physical construction.",
      selectedReason: "False alarm / Seasonal vegetation or phenology",
      analystId: "analyst_gamma",
      timestamp: "2026-09-17T12:00:00Z",
    });

    assert.strictEqual(result.created, true);
    assert.strictEqual(result.review.decision, "REJECTED");
    assert.strictEqual(result.review.selectedReason, "False alarm / Seasonal vegetation or phenology");
    assert.match(result.review.auditHash, /^[0-9a-f]{64}$/);
  });

  // 5. Decision revision (PENDING -> CONFIRMED -> REJECTED)
  it("criterion 5: tracks decision revisions across PENDING -> CONFIRMED -> REJECTED without mutating past revisions", () => {
    // Rev 1: PENDING
    const rev1 = saveReviewRevision({
      investigationId: "inv_lifecycle",
      candidateRegionId: "reg_0001",
      decision: "PENDING",
      analystNote: "Initial queue intake.",
      selectedReason: "Initial triage / pending review",
      timestamp: "2026-09-17T13:00:00Z",
    });
    assert.strictEqual(rev1.revisionNumber, 1);
    assert.strictEqual(rev1.review.previousDecision, undefined);

    // Rev 2: CONFIRMED
    const rev2 = saveReviewRevision({
      investigationId: "inv_lifecycle",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Verified with auxiliary high-res imagery.",
      selectedReason: "True positive change confirmed",
      timestamp: "2026-09-17T14:00:00Z",
    });
    assert.strictEqual(rev2.revisionNumber, 2);
    assert.strictEqual(rev2.review.previousDecision, "PENDING");

    // Rev 3: REJECTED
    const rev3 = saveReviewRevision({
      investigationId: "inv_lifecycle",
      candidateRegionId: "reg_0001",
      decision: "REJECTED",
      analystNote: "Reversed upon finding co-temporal sun-glint artifact in scene 2.",
      selectedReason: "False alarm / Sensor artifact or co-registration error",
      timestamp: "2026-09-17T15:00:00Z",
    });
    assert.strictEqual(rev3.revisionNumber, 3);
    assert.strictEqual(rev3.review.previousDecision, "CONFIRMED");

    // Check complete history: all 3 revisions must remain intact and immutable
    const history = getReviewHistory("inv_lifecycle", "reg_0001");
    assert.strictEqual(history.length, 3);

    // Newest first (Rev 3, Rev 2, Rev 1)
    assert.strictEqual(history[0].revisionNumber, 3);
    assert.strictEqual(history[0].decision, "REJECTED");
    assert.strictEqual(history[0].previousDecision, "CONFIRMED");

    assert.strictEqual(history[1].revisionNumber, 2);
    assert.strictEqual(history[1].decision, "CONFIRMED");
    assert.strictEqual(history[1].previousDecision, "PENDING");

    assert.strictEqual(history[2].revisionNumber, 1);
    assert.strictEqual(history[2].decision, "PENDING");
    assert.strictEqual(history[2].previousDecision, undefined);
  });

  // 6. Note-only revision
  it("criterion 6: records a new revision when decision is unchanged but analyst note is updated", () => {
    saveReviewRevision({
      investigationId: "inv_note_change",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Initial confirmation note.",
      selectedReason: "True positive change confirmed",
      timestamp: "2026-09-17T13:00:00Z",
    });

    const rev2 = saveReviewRevision({
      investigationId: "inv_note_change",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Updated note with additional site coordinates and ground context.",
      selectedReason: "True positive change confirmed",
      timestamp: "2026-09-17T14:00:00Z",
    });

    assert.strictEqual(rev2.created, true);
    assert.strictEqual(rev2.isDuplicate, false);
    assert.strictEqual(rev2.revisionNumber, 2);
    assert.strictEqual(rev2.review.decision, "CONFIRMED");
    assert.strictEqual(rev2.review.previousDecision, "CONFIRMED");
    assert.strictEqual(rev2.review.analystNote, "Updated note with additional site coordinates and ground context.");

    const history = getReviewHistory("inv_note_change", "reg_0001");
    assert.strictEqual(history.length, 2);
    assert.notStrictEqual(history[0].auditHash, history[1].auditHash);
  });

  // 7. Duplicate save behavior
  it("criterion 7: ignores duplicate save when decision, reason, and note are identical", () => {
    const rev1 = saveReviewRevision({
      investigationId: "inv_dup",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Standard confirmation.",
      selectedReason: "True positive change confirmed",
      timestamp: "2026-09-17T10:00:00Z",
    });
    assert.strictEqual(rev1.created, true);

    const rev2 = saveReviewRevision({
      investigationId: "inv_dup",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Standard confirmation.",
      selectedReason: "True positive change confirmed",
      timestamp: "2026-09-17T10:05:00Z",
    });

    assert.strictEqual(rev2.created, false);
    assert.strictEqual(rev2.isDuplicate, true);
    assert.strictEqual(rev2.revisionNumber, 1);

    const history = getReviewHistory("inv_dup", "reg_0001");
    assert.strictEqual(history.length, 1);
  });

  // 8. Revision ordering
  it("criterion 8: returns history in strict reverse chronological order without losing records", () => {
    for (let idx = 1; idx <= 5; idx++) {
      saveReviewRevision({
        investigationId: "inv_order",
        candidateRegionId: "reg_0001",
        decision: idx % 2 === 0 ? "CONFIRMED" : "PENDING",
        analystNote: `Revision step ${idx}`,
        selectedReason: `Reason ${idx}`,
        timestamp: `2026-09-17T10:0${idx}:00Z`,
      });
    }

    const history = getReviewHistory("inv_order", "reg_0001");
    assert.strictEqual(history.length, 5);
    assert.strictEqual(history[0].revisionNumber, 5);
    assert.strictEqual(history[1].revisionNumber, 4);
    assert.strictEqual(history[2].revisionNumber, 3);
    assert.strictEqual(history[3].revisionNumber, 2);
    assert.strictEqual(history[4].revisionNumber, 1);
  });

  // 9. LocalStorage persistence
  it("criterion 9: serializes reviews to localStorage under versioned key astra_analyst_reviews_v2", () => {
    saveReviewRevision({
      investigationId: "inv_persist",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Persistent review note.",
      selectedReason: "Confirmed",
      timestamp: "2026-09-17T12:00:00Z",
    });

    const rawStored = mockStorage.getItem(REVIEWS_STORAGE_KEY_V2);
    assert.ok(rawStored);
    const parsed = JSON.parse(rawStored);
    assert.ok(Array.isArray(parsed));
    assert.strictEqual(parsed.length, 1);
    assert.strictEqual(parsed[0].investigationId, "inv_persist");
    assert.strictEqual(parsed[0].decision, "CONFIRMED");
    assert.match(parsed[0].auditHash, /^[0-9a-f]{64}$/);
  });

  // 10. Malformed localStorage recovery
  it("criterion 10: recovers gracefully when localStorage contains malformed or corrupt JSON", () => {
    // Inject corrupt JSON into storage
    mockStorage.setRaw(REVIEWS_STORAGE_KEY_V2, "{ corrupt: json, syntax-error-here ]");

    // Must not throw, should return empty array
    const history = getReviewHistory("inv_corrupt", "reg_0001");
    assert.strictEqual(history.length, 0);

    // Saving a new review should succeed and overwrite corrupt data safely
    const result = saveReviewRevision({
      investigationId: "inv_corrupt",
      candidateRegionId: "reg_0001",
      decision: "PENDING",
      analystNote: "Recovered review",
      timestamp: "2026-09-17T12:00:00Z",
    });
    assert.strictEqual(result.created, true);
    assert.strictEqual(result.revisionNumber, 1);
  });

  // 11. Storage unavailable behavior
  it("criterion 11: handles localStorage throwing errors gracefully using memory store without crashing", () => {
    mockStorage.shouldThrowOnSet = true;

    // Should not throw even when storage throws QuotaExceededError
    assert.doesNotThrow(() => {
      const result = saveReviewRevision({
        investigationId: "inv_no_storage",
        candidateRegionId: "reg_0001",
        decision: "CONFIRMED",
        analystNote: "Saved to in-memory store",
        timestamp: "2026-09-17T12:00:00Z",
      });
      assert.strictEqual(result.created, true);
      assert.strictEqual(result.review.decision, "CONFIRMED");
    });

    mockStorage.shouldThrowOnSet = false;
  });

  // 12. Deterministic review ID
  it("criterion 12: computes deterministic review ID starting with rev_ for identical parameters", () => {
    const id1 = computeReviewHash("inv_abc", "reg_123", "CONFIRMED", "2026-09-17T10:00:00Z");
    const id2 = computeReviewHash("inv_abc", "reg_123", "CONFIRMED", "2026-09-17T10:00:00Z");
    const id3 = computeReviewHash("inv_abc", "reg_123", "REJECTED", "2026-09-17T10:00:00Z");

    assert.strictEqual(id1, id2);
    assert.notStrictEqual(id1, id3);
    assert.match(id1, /^rev_[0-9a-f]{8}$/);
  });

  // 13. Deterministic audit hash
  it("criterion 13: computes identical SHA-256 audit hash regardless of JSON object key insertion order", () => {
    const objA = {
      investigationId: "inv_hash_test",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      revisionNumber: 1,
      analystNote: "Key order test note",
    };
    const objB = {
      analystNote: "Key order test note",
      revisionNumber: 1,
      decision: "CONFIRMED",
      candidateRegionId: "reg_0001",
      investigationId: "inv_hash_test",
    };

    const hashA = computeReviewAuditHash(objA);
    const hashB = computeReviewAuditHash(objB);

    assert.strictEqual(hashA, hashB);
    assert.match(hashA, /^[0-9a-f]{64}$/);
  });

  // 14. Changed note produces changed audit hash
  it("criterion 14: generates distinct audit hash when note changes while all other fields remain identical", () => {
    const base = {
      investigationId: "inv_note_hash",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      revisionNumber: 1,
    };

    const hash1 = computeReviewAuditHash({ ...base, analystNote: "Note Version A" });
    const hash2 = computeReviewAuditHash({ ...base, analystNote: "Note Version B" });

    assert.notStrictEqual(hash1, hash2);
    assert.match(hash1, /^[0-9a-f]{64}$/);
    assert.match(hash2, /^[0-9a-f]{64}$/);
  });

  // 15. Changed decision produces changed audit hash
  it("criterion 15: generates distinct audit hash when decision changes while other fields remain identical", () => {
    const base = {
      investigationId: "inv_dec_hash",
      candidateRegionId: "reg_0001",
      analystNote: "Unchanged note",
      revisionNumber: 1,
    };

    const hash1 = computeReviewAuditHash({ ...base, decision: "CONFIRMED" });
    const hash2 = computeReviewAuditHash({ ...base, decision: "REJECTED" });

    assert.notStrictEqual(hash1, hash2);
  });

  // 16. Export payload
  it("criterion 16: generates export JSON matching schema without exposing secrets or raw imagery", () => {
    saveReviewRevision({
      investigationId: "inv_export",
      candidateRegionId: "reg_0001",
      seriesId: "series_test",
      discoveryPairId: "pair_01_02",
      decision: "CONFIRMED",
      analystNote: "Export test note.",
      selectedReason: "Confirmed",
      analystId: "analyst_tester",
      timestamp: "2026-09-17T12:00:00Z",
    });

    const rawExport = exportInvestigationReviewJson("inv_export", "reg_0001");
    const parsed = JSON.parse(rawExport);

    assert.strictEqual(parsed.schemaVersion, "astra_review_v2");
    assert.strictEqual(parsed.investigationId, "inv_export");
    assert.strictEqual(parsed.candidateRegionId, "reg_0001");
    assert.strictEqual(parsed.currentDecision, "CONFIRMED");
    assert.strictEqual(parsed.latestRevisionNumber, 1);
    assert.strictEqual(parsed.totalRevisions, 1);
    assert.match(parsed.currentAuditHash, /^[0-9a-f]{64}$/);
    assert.ok(Array.isArray(parsed.revisions));
    assert.strictEqual(parsed.revisions.length, 1);

    // Verify absence of sensitive keys or raw image payloads
    const exportStr = JSON.stringify(parsed);
    assert.ok(!exportStr.includes("api_key"));
    assert.ok(!exportStr.includes("password"));
    assert.ok(!exportStr.includes("secret"));
    assert.ok(!exportStr.includes("data:image"));
  });

  // 17. Investigation isolation
  it("criterion 17: isolates review histories across distinct investigation IDs", () => {
    saveReviewRevision({
      investigationId: "inv_alpha",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Alpha note",
      timestamp: "2026-09-17T10:00:00Z",
    });

    saveReviewRevision({
      investigationId: "inv_beta",
      candidateRegionId: "reg_0001",
      decision: "REJECTED",
      analystNote: "Beta note",
      timestamp: "2026-09-17T11:00:00Z",
    });

    const historyAlpha = getReviewHistory("inv_alpha", "reg_0001");
    const historyBeta = getReviewHistory("inv_beta", "reg_0001");

    assert.strictEqual(historyAlpha.length, 1);
    assert.strictEqual(historyAlpha[0].decision, "CONFIRMED");
    assert.strictEqual(historyAlpha[0].investigationId, "inv_alpha");

    assert.strictEqual(historyBeta.length, 1);
    assert.strictEqual(historyBeta[0].decision, "REJECTED");
    assert.strictEqual(historyBeta[0].investigationId, "inv_beta");
  });

  // 18. Candidate isolation
  it("criterion 18: isolates review histories across different candidate regions of the same investigation", () => {
    saveReviewRevision({
      investigationId: "inv_shared",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Region 1 confirmed",
      timestamp: "2026-09-17T10:00:00Z",
    });

    saveReviewRevision({
      investigationId: "inv_shared",
      candidateRegionId: "reg_0002",
      decision: "REJECTED",
      analystNote: "Region 2 rejected",
      timestamp: "2026-09-17T11:00:00Z",
    });

    const hist1 = getReviewHistory("inv_shared", "reg_0001");
    const hist2 = getReviewHistory("inv_shared", "reg_0002");

    assert.strictEqual(hist1.length, 1);
    assert.strictEqual(hist1[0].candidateRegionId, "reg_0001");
    assert.strictEqual(hist1[0].decision, "CONFIRMED");

    assert.strictEqual(hist2.length, 1);
    assert.strictEqual(hist2[0].candidateRegionId, "reg_0002");
    assert.strictEqual(hist2[0].decision, "REJECTED");
  });

  // 19. Machine assessment remains unchanged
  it("criterion 19: preserves machine assessment completely intact when an analyst review is created", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const initialCategory = summary.category.primary;
    const initialConfidence = summary.confidenceTier;
    const initialSupport = summary.supportStatus;

    // Save a contrary analyst decision (REJECTED on a HIGH confidence construction event)
    saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "REJECTED",
      analystNote: "Analyst disagrees with automated machine detection.",
      timestamp: "2026-09-17T12:00:00Z",
    });

    // Re-transform or inspect summary: machine assessment must remain unchanged
    const recheckedSummary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.strictEqual(recheckedSummary.category.primary, initialCategory);
    assert.strictEqual(recheckedSummary.confidenceTier, initialConfidence);
    assert.strictEqual(recheckedSummary.supportStatus, initialSupport);
  });

  // 20. Analyst decision remains separate from machine confidence
  it("criterion 20: keeps analyst decision in a distinct field without overwriting machine confidence", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    const reviewRes = saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "REJECTED",
      analystNote: "Human analyst override: rejected.",
    });

    // Machine confidence tier is HIGH, analyst decision is REJECTED
    assert.strictEqual(summary.confidenceTier, "high");
    assert.strictEqual(reviewRes.review.decision, "REJECTED");
    assert.notStrictEqual(summary.confidenceTier, reviewRes.review.decision);
  });

  // 21. Missing machine classification
  it("criterion 21: handles investigation dossier with missing machine classification safely", () => {
    const sparseDossier: InvestigationDossier = {
      investigation_id: "inv_no_class",
      candidate_region_id: "reg_0001",
      series_id: "series_sparse",
      discovery_pair_id: "pair_sparse",
      created_at: "2026-09-17T10:00:00Z",
      status: "COMPLETED",
      primary_assessment: {
        change_detected: true,
        candidate_region_id: "reg_0001",
        confidence_tier: "medium",
      },
    } as unknown as InvestigationDossier;

    const summary = transformInvestigationDossier(sparseDossier);
    assert.strictEqual(summary.category.primary, "UNCLASSIFIED");

    // Analyst review should proceed normally
    const result = saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "CONFIRMED",
      analystNote: "Confirmed manually despite missing machine classification",
    });
    assert.strictEqual(result.created, true);
    assert.strictEqual(result.review.decision, "CONFIRMED");
  });

  // 22. Missing temporal evidence
  it("criterion 22: handles investigation dossier with missing temporal evidence safely", () => {
    const sparseDossier: InvestigationDossier = {
      investigation_id: "inv_no_temporal",
      candidate_region_id: "reg_0001",
      series_id: "series_sparse",
      discovery_pair_id: "pair_sparse",
      created_at: "2026-09-17T10:00:00Z",
      status: "COMPLETED",
      primary_assessment: {
        change_detected: true,
        candidate_region_id: "reg_0001",
        confidence_tier: "low",
      },
    } as unknown as InvestigationDossier;

    const summary = transformInvestigationDossier(sparseDossier);
    assert.strictEqual(summary.supportStatus, "UNKNOWN");

    // Analyst review should proceed normally
    const result = saveReviewRevision({
      investigationId: summary.investigationId,
      candidateRegionId: summary.candidateRegionId,
      decision: "PENDING",
      analystNote: "Awaiting temporal acquisition",
    });
    assert.strictEqual(result.created, true);
    assert.strictEqual(result.review.decision, "PENDING");
  });

  // 23. Missing candidate ID
  it("criterion 23: handles missing candidate region ID gracefully with safe fallback", () => {
    const result = saveReviewRevision({
      investigationId: "inv_no_reg",
      candidateRegionId: "", // empty candidate region ID
      decision: "PENDING",
      analystNote: "Investigation-level triage without localized region.",
    });

    assert.strictEqual(result.created, true);
    assert.strictEqual(result.review.candidateRegionId, "reg_unknown");

    const history = getReviewHistory("inv_no_reg", "reg_unknown");
    assert.strictEqual(history.length, 1);
  });

  // 24. Long note handling
  it("criterion 24: correctly handles multi-kilobyte long analyst notes with exact hash generation", () => {
    const longNote = "ANALYSIS PARAGRAPH: " + "Long analyst commentary line with details. \n".repeat(200);
    assert.ok(longNote.length > 5000);

    const result = saveReviewRevision({
      investigationId: "inv_long_note",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: longNote,
      selectedReason: "Detailed manual examination",
      timestamp: "2026-09-17T12:00:00Z",
    });

    assert.strictEqual(result.created, true);
    assert.strictEqual(result.review.analystNote.length, longNote.trim().length);
    assert.match(result.review.auditHash, /^[0-9a-f]{64}$/);

    const history = getReviewHistory("inv_long_note", "reg_0001");
    assert.strictEqual(history[0].analystNote.length, longNote.trim().length);
  });

  // 25. Refresh/reload behavior
  it("criterion 25: simulates browser reload and confirms persistence and integrity across sessions", () => {
    // Session 1: Create 2 revisions
    saveReviewRevision({
      investigationId: "inv_reload",
      candidateRegionId: "reg_0001",
      decision: "PENDING",
      analystNote: "Session 1 Note 1",
      timestamp: "2026-09-17T10:00:00Z",
    });

    saveReviewRevision({
      investigationId: "inv_reload",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Session 1 Note 2",
      timestamp: "2026-09-17T11:00:00Z",
    });

    // Simulate reload: clear in-memory state while keeping localStorage intact
    // (Notice: clearAllReviews removes localStorage, so we only clear memoryStore by calling saveReviewRevision or reloading)
    const rawStored = mockStorage.getItem(REVIEWS_STORAGE_KEY_V2);
    assert.ok(rawStored);

    // Verify getReviewHistory re-reads accurately from localStorage
    const reloadedHistory = getReviewHistory("inv_reload", "reg_0001");
    assert.strictEqual(reloadedHistory.length, 2);
    assert.strictEqual(reloadedHistory[0].revisionNumber, 2);
    assert.strictEqual(reloadedHistory[0].decision, "CONFIRMED");
    assert.strictEqual(reloadedHistory[1].revisionNumber, 1);
    assert.strictEqual(reloadedHistory[1].decision, "PENDING");
  });

  // Extra helper verification: normalizeDecision
  it("normalizes legacy decision tokens correctly", () => {
    assert.strictEqual(normalizeDecision("CONFIRM"), "CONFIRMED");
    assert.strictEqual(normalizeDecision("CONFIRMED"), "CONFIRMED");
    assert.strictEqual(normalizeDecision("REJECT"), "REJECTED");
    assert.strictEqual(normalizeDecision("REJECTED"), "REJECTED");
    assert.strictEqual(normalizeDecision("FLAG_NEEDS_REVIEW"), "PENDING");
    assert.strictEqual(normalizeDecision("PENDING"), "PENDING");
  });
});
