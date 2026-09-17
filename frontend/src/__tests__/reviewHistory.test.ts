/**
 * Unit Tests for ReviewHistory Component & Logic
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  saveReviewRevision,
  getReviewHistory,
  clearAllReviews,
} from "../services/reviewStore.ts";

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

describe("Milestone D9: ReviewHistory Logic Unit Tests", () => {
  beforeEach(() => {
    mockStorage.clear();
    clearAllReviews();
  });

  it("returns empty history state when no reviews exist", () => {
    const history = getReviewHistory("inv_empty", "reg_0001");
    assert.strictEqual(history.length, 0);
  });

  it("tracks single review revision details correctly", () => {
    const res = saveReviewRevision({
      investigationId: "inv_single",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Confirmed physical excavation.",
      selectedReason: "True positive change confirmed",
      analystId: "analyst_alpha",
      timestamp: "2026-09-17T12:00:00Z",
    });

    assert.strictEqual(res.review.revisionNumber, 1);
    assert.strictEqual(res.review.decision, "CONFIRMED");
    assert.strictEqual(res.review.previousDecision, undefined);
    assert.match(res.review.auditHash, /^[0-9a-f]{64}$/);

    const history = getReviewHistory("inv_single", "reg_0001");
    assert.strictEqual(history.length, 1);
    assert.strictEqual(history[0].reviewId, res.review.reviewId);
  });

  it("renders chronological progression with previous decision markers", () => {
    saveReviewRevision({
      investigationId: "inv_seq",
      candidateRegionId: "reg_0001",
      decision: "PENDING",
      analystNote: "Initial triage",
      timestamp: "2026-09-17T10:00:00Z",
    });

    saveReviewRevision({
      investigationId: "inv_seq",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Confirmed by senior analyst",
      timestamp: "2026-09-17T11:00:00Z",
    });

    saveReviewRevision({
      investigationId: "inv_seq",
      candidateRegionId: "reg_0001",
      decision: "REJECTED",
      analystNote: "Reversed after multi-spectral cloud check",
      timestamp: "2026-09-17T12:00:00Z",
    });

    const history = getReviewHistory("inv_seq", "reg_0001");
    assert.strictEqual(history.length, 3);

    // Latest (Rev 3)
    assert.strictEqual(history[0].revisionNumber, 3);
    assert.strictEqual(history[0].decision, "REJECTED");
    assert.strictEqual(history[0].previousDecision, "CONFIRMED");

    // Rev 2
    assert.strictEqual(history[1].revisionNumber, 2);
    assert.strictEqual(history[1].decision, "CONFIRMED");
    assert.strictEqual(history[1].previousDecision, "PENDING");

    // Rev 1
    assert.strictEqual(history[2].revisionNumber, 1);
    assert.strictEqual(history[2].decision, "PENDING");
    assert.strictEqual(history[2].previousDecision, undefined);
  });

  it("preserves exact SHA-256 audit hashes for copy and reference", () => {
    const res = saveReviewRevision({
      investigationId: "inv_hash_check",
      candidateRegionId: "reg_0001",
      decision: "CONFIRMED",
      analystNote: "Testing hash integrity",
      timestamp: "2026-09-17T14:00:00Z",
    });

    const history = getReviewHistory("inv_hash_check", "reg_0001");
    assert.strictEqual(history[0].auditHash, res.review.auditHash);
    assert.strictEqual(history[0].auditHash.length, 64);
  });
});
