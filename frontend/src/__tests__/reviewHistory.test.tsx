/// <reference types="node" />

/**
 * Component Type-Checking and Unit Verification for ReviewHistory
 *
 * Validates ReviewHistory props contract and React element creation.
 */

import React from "react";
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { ReviewHistory } from "../components/investigation/ReviewHistory.tsx";
import type { AnalystReviewRecord } from "../types/models.ts";

describe("ReviewHistory Component Tests", () => {
  it("instantiates ReviewHistory with empty history array", () => {
    const element = React.createElement(ReviewHistory, {
      history: [],
      candidateRegionId: "reg_0001",
    });

    assert.ok(element);
    assert.strictEqual(element.type, ReviewHistory);
    assert.strictEqual(element.props.history.length, 0);
    assert.strictEqual(element.props.candidateRegionId, "reg_0001");
  });

  it("instantiates ReviewHistory with populated revision items", () => {
    const mockRecords: AnalystReviewRecord[] = [
      {
        reviewId: "rev_inv_test_reg_0001_r2",
        investigationId: "inv_test",
        candidateRegionId: "reg_0001",
        seriesId: "series_s2",
        discoveryPairId: "pair_01",
        createdAt: "2026-09-17T10:00:00Z",
        updatedAt: "2026-09-17T11:00:00Z",
        decision: "CONFIRMED",
        previousDecision: "PENDING",
        revisionNumber: 2,
        analystNote: "Confirmed physical excavation",
        selectedReason: "True positive change confirmed",
        reasonCode: "True positive change confirmed",
        analystId: "analyst_beta",
        auditHash: "a".repeat(64),
      },
      {
        reviewId: "rev_inv_test_reg_0001_r1",
        investigationId: "inv_test",
        candidateRegionId: "reg_0001",
        seriesId: "series_s2",
        discoveryPairId: "pair_01",
        createdAt: "2026-09-17T10:00:00Z",
        updatedAt: "2026-09-17T10:00:00Z",
        decision: "PENDING",
        revisionNumber: 1,
        analystNote: "Initial intake",
        selectedReason: "Needs review",
        reasonCode: "Needs review",
        analystId: "analyst_alpha",
        auditHash: "b".repeat(64),
      },
    ];

    const element = React.createElement(ReviewHistory, {
      history: mockRecords,
      candidateRegionId: "reg_0001",
    });

    assert.ok(element);
    assert.strictEqual(element.props.history.length, 2);
    assert.strictEqual(element.props.history[0].decision, "CONFIRMED");
    assert.strictEqual(element.props.history[1].decision, "PENDING");
    assert.strictEqual(element.props.candidateRegionId, "reg_0001");
  });
});
