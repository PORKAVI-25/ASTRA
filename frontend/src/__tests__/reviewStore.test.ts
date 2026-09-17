/**
 * Unit Tests for Analyst Review Local Store
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  computeReviewHash,
  createAnalystReview,
  deleteReview,
  exportReviewsAsJson,
  getAllReviews,
  getReviewsForInvestigation,
  saveReview,
} from "../services/reviewStore.ts";

// In-memory mock for localStorage in node test environment
class MockLocalStorage {
  private store: Record<string, string> = {};

  getItem(key: string): string | null {
    return this.store[key] || null;
  }
  setItem(key: string, value: string): void {
    this.store[key] = value;
  }
  removeItem(key: string): void {
    delete this.store[key];
  }
  clear(): void {
    this.store = {};
  }
}

// Attach mock window & localStorage
const mockStorage = new MockLocalStorage();
(globalThis as any).window = {
  localStorage: mockStorage,
};

describe("Analyst Review Store Unit Tests", () => {
  beforeEach(() => {
    mockStorage.clear();
  });

  it("computeReviewHash produces deterministic hash starting with rev_", () => {
    const hash1 = computeReviewHash("inv_123", "reg_0001", "CONFIRM", "2026-04-15T10:00:00Z");
    const hash2 = computeReviewHash("inv_123", "reg_0001", "CONFIRM", "2026-04-15T10:00:00Z");
    const hash3 = computeReviewHash("inv_123", "reg_0001", "REJECT", "2026-04-15T10:00:00Z");

    assert.strictEqual(hash1, hash2);
    assert.notStrictEqual(hash1, hash3);
    assert.match(hash1, /^rev_[0-9a-f]{8}$/);
  });

  it("createAnalystReview constructs complete review record", () => {
    const review = createAnalystReview({
      investigationId: "inv_test",
      candidateRegionId: "reg_0002",
      decision: "CONFIRM",
      comments: "Verified construction onset at T2",
      analystId: "analyst_porkavi",
      confidenceRating: 5,
      timestamp: "2026-04-15T12:00:00Z",
    });

    assert.strictEqual(review.investigationId, "inv_test");
    assert.strictEqual(review.candidateRegionId, "reg_0002");
    assert.strictEqual(review.decision, "CONFIRM");
    assert.strictEqual(review.analystId, "analyst_porkavi");
    assert.strictEqual(review.confidenceRating, 5);
    assert.match(review.reviewId, /^rev_/);
  });

  it("saveReview and getAllReviews persists across calls", () => {
    const review1 = createAnalystReview({
      investigationId: "inv_1",
      candidateRegionId: "reg_0001",
      decision: "CONFIRM",
      timestamp: "2026-04-15T10:00:00Z",
    });
    const review2 = createAnalystReview({
      investigationId: "inv_2",
      candidateRegionId: "reg_0002",
      decision: "FLAG_NEEDS_REVIEW",
      timestamp: "2026-04-15T11:00:00Z",
    });

    saveReview(review1);
    saveReview(review2);

    const all = getAllReviews();
    assert.strictEqual(all.length, 2);
    assert.strictEqual(all[0].investigationId, "inv_2"); // LIFO ordering
    assert.strictEqual(all[1].investigationId, "inv_1");
  });

  it("getReviewsForInvestigation filters correctly by investigation ID", () => {
    const review1 = createAnalystReview({
      investigationId: "inv_target",
      candidateRegionId: "reg_0001",
      decision: "CONFIRM",
      timestamp: "2026-04-15T10:00:00Z",
    });
    const review2 = createAnalystReview({
      investigationId: "inv_other",
      candidateRegionId: "reg_0002",
      decision: "REJECT",
      timestamp: "2026-04-15T11:00:00Z",
    });

    saveReview(review1);
    saveReview(review2);

    const filtered = getReviewsForInvestigation("inv_target");
    assert.strictEqual(filtered.length, 1);
    assert.strictEqual(filtered[0].candidateRegionId, "reg_0001");
  });

  it("deleteReview removes review by ID", () => {
    const review = createAnalystReview({
      investigationId: "inv_del",
      candidateRegionId: "reg_0001",
      decision: "REJECT",
      timestamp: "2026-04-15T10:00:00Z",
    });

    saveReview(review);
    assert.strictEqual(getAllReviews().length, 1);

    deleteReview(review.reviewId);
    assert.strictEqual(getAllReviews().length, 0);
  });

  it("exportReviewsAsJson exports formatted JSON with metadata", () => {
    const review = createAnalystReview({
      investigationId: "inv_exp",
      candidateRegionId: "reg_0001",
      decision: "CONFIRM",
      timestamp: "2026-04-15T10:00:00Z",
    });
    saveReview(review);

    const exported = exportReviewsAsJson();
    const parsed = JSON.parse(exported);

    assert.strictEqual(parsed.record_count, 1);
    assert.strictEqual(parsed.reviews[0].investigationId, "inv_exp");
    assert.ok(parsed.exported_at);
  });
});
