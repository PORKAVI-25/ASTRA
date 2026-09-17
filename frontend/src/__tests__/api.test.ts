/**
 * Unit Tests for Strongly Typed API Client
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { ApiError, getChangeMaskUrl } from "../services/api.ts";

describe("API Client Unit Tests", () => {
  it("ApiError properly encapsulates HTTP status, errorCode, stage, and details", () => {
    const err = new ApiError(
      400,
      "TemporalSeries 'series_missing' does not exist.",
      "VALIDATION_ERROR",
      "series_resolution",
      { series_id: "series_missing" }
    );

    assert.strictEqual(err.name, "ApiError");
    assert.strictEqual(err.status, 400);
    assert.strictEqual(err.errorCode, "VALIDATION_ERROR");
    assert.strictEqual(err.stage, "series_resolution");
    assert.strictEqual(err.message, "TemporalSeries 'series_missing' does not exist.");
    assert.deepStrictEqual(err.details, { series_id: "series_missing" });
    assert.ok(err instanceof Error);
  });

  it("getChangeMaskUrl constructs deterministic PNG URL", () => {
    const url = getChangeMaskUrl("cdr_pair_01__02");
    assert.match(url, /\/api\/v1\/change-detection\/cdr_pair_01__02\/mask$/);
  });

  it("getChangeMaskUrl properly encodes special characters in resultId", () => {
    const url = getChangeMaskUrl("cdr_pair 01/02");
    assert.match(url, /cdr_pair%2001%2F02/);
  });
});
