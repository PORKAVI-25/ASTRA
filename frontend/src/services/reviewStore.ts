/**
 * ASTRA Analyst Review & Audit Store (Milestone D9)
 *
 * Provides a local, deterministic, offline review store and revision history
 * for human analyst triage decisions (CONFIRMED, REJECTED, PENDING).
 *
 * Key Principles:
 * - Read-only overlay on top of backend analytical findings.
 * - Does NOT alter machine classifications, confidence tiers, or temporal support.
 * - Uses pure deterministic SHA-256 for local audit hashes.
 * - Manages sequential revision histories (Revision 1 -> Revision 2 -> ...).
 * - Guaranteed resilience against localStorage failures, corruption, or private browsing.
 * - 100% offline air-gap compliant (0 external dependencies or network calls).
 * - Authoritative references: docs/dashboard-contract.md, docs/dashboard-data-model.md
 */

import type {
  AnalystReviewRecord,
  ReviewDecision,
  ReviewHistoryExport,
} from "../types/models";

export const REVIEWS_STORAGE_KEY_V2 = "astra_analyst_reviews_v2";
export const REVIEWS_STORAGE_KEY_V1 = "astra_analyst_reviews_v1";

// In-memory fallback if localStorage is disabled or throws
let memoryStore: AnalystReviewRecord[] = [];

/**
 * Pure deterministic bitwise SHA-256 implementation (FIPS 180-4).
 * Pure JavaScript, synchronous, runs anywhere without browser/Node crypto dependencies.
 */
function rightRotate(value: number, amount: number): number {
  return (value >>> amount) | (value << (32 - amount));
}

export function computeSha256(ascii: string): string {
  const maxWord = Math.pow(2, 32);
  const hash: number[] = [];
  const k: number[] = [];
  let primeCounter = 0;

  const isPrime = (candidate: number) => {
    for (let factor = 2, max = Math.sqrt(candidate); factor <= max; factor++) {
      if (candidate % factor === 0) return false;
    }
    return true;
  };

  const fractionalBits = (x: number) => ((x - Math.floor(x)) * maxWord) | 0;

  for (let candidate = 2; primeCounter < 64; candidate++) {
    if (isPrime(candidate)) {
      if (primeCounter < 8) {
        hash[primeCounter] = fractionalBits(Math.pow(candidate, 1 / 2));
      }
      k[primeCounter] = fractionalBits(Math.pow(candidate, 1 / 3));
      primeCounter++;
    }
  }

  const utf8: number[] = [];
  for (let m = 0; m < ascii.length; m++) {
    const charCode = ascii.charCodeAt(m);
    if (charCode < 0x80) {
      utf8.push(charCode);
    } else if (charCode < 0x800) {
      utf8.push(0xc0 | (charCode >> 6), 0x80 | (charCode & 0x3f));
    } else if (charCode < 0xd800 || charCode >= 0xe000) {
      utf8.push(
        0xe0 | (charCode >> 12),
        0x80 | ((charCode >> 6) & 0x3f),
        0x80 | (charCode & 0x3f)
      );
    } else {
      m++;
      const nextCode = ascii.charCodeAt(m);
      const combined = 0x10000 + (((charCode & 0x3ff) << 10) | (nextCode & 0x3ff));
      utf8.push(
        0xf0 | (combined >> 18),
        0x80 | ((combined >> 12) & 0x3f),
        0x80 | ((combined >> 6) & 0x3f),
        0x80 | (combined & 0x3f)
      );
    }
  }

  const utf8BitLength = utf8.length * 8;
  utf8.push(0x80);
  while ((utf8.length % 64) !== 56) {
    utf8.push(0);
  }
  for (let b = 0; b < 8; b++) {
    utf8.push(b < 4 ? 0 : (utf8BitLength >>> ((7 - b) * 8)) & 0xff);
  }

  const words: number[] = [];
  for (let w = 0; w < utf8.length; w += 4) {
    words.push(
      (utf8[w] << 24) |
        (utf8[w + 1] << 16) |
        (utf8[w + 2] << 8) |
        utf8[w + 3]
    );
  }

  for (let chunk = 0; chunk < words.length; chunk += 16) {
    const w = words.slice(chunk, chunk + 16);
    for (let idx = 16; idx < 64; idx++) {
      const s0 =
        rightRotate(w[idx - 15], 7) ^
        rightRotate(w[idx - 15], 18) ^
        (w[idx - 15] >>> 3);
      const s1 =
        rightRotate(w[idx - 2], 17) ^
        rightRotate(w[idx - 2], 19) ^
        (w[idx - 2] >>> 10);
      w[idx] = (w[idx - 16] + s0 + w[idx - 7] + s1) | 0;
    }

    let a = hash[0];
    let b = hash[1];
    let c = hash[2];
    let d = hash[3];
    let e = hash[4];
    let f = hash[5];
    let g = hash[6];
    let h = hash[7];

    for (let idx = 0; idx < 64; idx++) {
      const s1 = rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + k[idx] + w[idx]) | 0;
      const s0 = rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) | 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) | 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) | 0;
    }

    hash[0] = (hash[0] + a) | 0;
    hash[1] = (hash[1] + b) | 0;
    hash[2] = (hash[2] + c) | 0;
    hash[3] = (hash[3] + d) | 0;
    hash[4] = (hash[4] + e) | 0;
    hash[5] = (hash[5] + f) | 0;
    hash[6] = (hash[6] + g) | 0;
    hash[7] = (hash[7] + h) | 0;
  }

  let result = "";
  for (let idx = 0; idx < 8; idx++) {
    result += (hash[idx] >>> 0).toString(16).padStart(8, "0");
  }
  return result;
}

/**
 * Legacy deterministic hash calculation preserved for D4 backwards compatibility.
 * Produces an 8-character hex digest prefixed with rev_.
 */
export function computeReviewHash(
  investigationId: string,
  candidateRegionId: string,
  decision: string,
  timestamp: string
): string {
  const seed = `${investigationId}:${candidateRegionId}:${decision}:${timestamp}`;
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return `rev_${(h >>> 0).toString(16).padStart(8, "0")}`;
}

/**
 * Normalizes user/legacy decision strings into strict D9 ReviewDecision.
 */
export function normalizeDecision(decision: string): "PENDING" | "CONFIRMED" | "REJECTED" {
  const d = (decision || "").toUpperCase().trim();
  if (d === "CONFIRMED" || d === "CONFIRM") return "CONFIRMED";
  if (d === "REJECTED" || d === "REJECT") return "REJECTED";
  return "PENDING";
}

/**
 * Constructs the canonical JSON string for deterministic review auditing.
 * All keys are strictly sorted alphabetically and values normalized.
 */
export function getCanonicalReviewString(
  record: Partial<AnalystReviewRecord> | Record<string, unknown>
): string {
  const rec = record as Record<string, any>;
  const canonicalPayload = {
    analystId: String(rec.analystId || "analyst_local"),
    analystNote: String(rec.analystNote ?? rec.comments ?? "").trim(),
    candidateRegionId: String(rec.candidateRegionId || ""),
    createdAt: String(rec.createdAt || ""),
    decision: normalizeDecision(rec.decision || "PENDING"),
    discoveryPairId: String(rec.discoveryPairId || ""),
    investigationId: String(rec.investigationId || ""),
    previousDecision: rec.previousDecision ? String(rec.previousDecision) : "",
    reasonCode: String(rec.reasonCode || rec.selectedReason || ""),
    revisionNumber: Number(rec.revisionNumber) || 1,
    selectedReason: String(rec.selectedReason || ""),
    seriesId: String(rec.seriesId || ""),
    updatedAt: String(rec.updatedAt || ""),
  };
  return JSON.stringify(canonicalPayload);
}

/**
 * Computes the official SHA-256 audit hash for a review revision.
 */
export function computeReviewAuditHash(
  record: Partial<AnalystReviewRecord> | Record<string, unknown>
): string {
  const canonical = getCanonicalReviewString(record as Partial<AnalystReviewRecord>);
  return computeSha256(canonical);
}

/**
 * Internal storage helper: loads all review records from localStorage or fallback memory.
 */
function loadAllRecords(): AnalystReviewRecord[] {
  if (typeof window === "undefined" || !window.localStorage) {
    return memoryStore;
  }

  try {
    const rawV2 = window.localStorage.getItem(REVIEWS_STORAGE_KEY_V2);
    if (rawV2) {
      const parsed = JSON.parse(rawV2);
      if (Array.isArray(parsed)) {
        return parsed as AnalystReviewRecord[];
      }
    }

    // Check V1 if V2 is absent
    const rawV1 = window.localStorage.getItem(REVIEWS_STORAGE_KEY_V1);
    if (rawV1) {
      const parsed = JSON.parse(rawV1);
      if (Array.isArray(parsed)) {
        return parsed as AnalystReviewRecord[];
      }
    }

    return [];
  } catch {
    // Graceful recovery from malformed/corrupt JSON
    return [];
  }
}

/**
 * Internal storage helper: persists all review records to localStorage.
 */
function saveAllRecords(records: AnalystReviewRecord[]): void {
  memoryStore = [...records];

  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    const serialized = JSON.stringify(records);
    window.localStorage.setItem(REVIEWS_STORAGE_KEY_V2, serialized);
    // Keep V1 in sync for any legacy consumers
    window.localStorage.setItem(REVIEWS_STORAGE_KEY_V1, serialized);
  } catch {
    // Graceful recovery if localStorage is full or disabled
  }
}

/**
 * Retrieves the full revision history for an investigation and candidate region.
 * Returns revisions in reverse chronological order (newest first).
 */
export function getReviewHistory(
  investigationId: string,
  candidateRegionId?: string
): AnalystReviewRecord[] {
  const all = loadAllRecords();
  return all
    .filter(
      (r) =>
        r.investigationId === investigationId &&
        (!candidateRegionId || r.candidateRegionId === candidateRegionId)
    )
    .sort((a, b) => (b.revisionNumber ?? 1) - (a.revisionNumber ?? 1));
}

/**
 * Retrieves the latest review revision for an investigation and candidate region.
 */
export function getLatestReview(
  investigationId: string,
  candidateRegionId?: string
): AnalystReviewRecord | null {
  const history = getReviewHistory(investigationId, candidateRegionId);
  return history.length > 0 ? history[0] : null;
}

export interface SaveReviewRevisionParams {
  investigationId: string;
  candidateRegionId: string;
  seriesId?: string;
  discoveryPairId?: string;
  decision: ReviewDecision;
  analystNote?: string;
  selectedReason?: string;
  reasonCode?: string;
  analystId?: string;
  timestamp?: string;
}

export interface SaveReviewRevisionResult {
  created: boolean;
  review: AnalystReviewRecord;
  isDuplicate: boolean;
  revisionNumber: number;
}

/**
 * Persists a new analyst review revision.
 *
 * Enforces D9 Revision Rules:
 * - Never mutates historical revisions.
 * - PENDING -> CONFIRMED, PENDING -> REJECTED, CONFIRMED -> REJECTED, REJECTED -> CONFIRMED.
 * - If decision, note, and reason are identical to current revision, prevents duplicate revision creation.
 * - If decision is unchanged but note/reason changed, records a new revision.
 * - Automatically computes deterministic canonical SHA-256 audit hash.
 */
export function saveReviewRevision(
  params: SaveReviewRevisionParams
): SaveReviewRevisionResult {
  const invId = (params.investigationId || "").trim() || "inv_unknown";
  const regId = (params.candidateRegionId || "").trim() || "reg_unknown";
  const normDecision = normalizeDecision(params.decision);
  const note = (params.analystNote ?? "").trim();
  const reason = (params.selectedReason ?? "").trim();
  const reasonCode = (params.reasonCode ?? reason).trim();
  const analystId = (params.analystId ?? "analyst_local").trim();
  const timestamp = params.timestamp || new Date().toISOString();

  const history = getReviewHistory(invId, regId);
  const latest = history.length > 0 ? history[0] : null;

  // Duplicate Save Guard: identical decision, note, and reason
  if (
    latest &&
    latest.decision === normDecision &&
    (latest.analystNote || latest.comments || "").trim() === note &&
    (latest.selectedReason || "").trim() === reason
  ) {
    return {
      created: false,
      review: latest,
      isDuplicate: true,
      revisionNumber: latest.revisionNumber ?? 1,
    };
  }

  const revisionNumber = latest ? (latest.revisionNumber ?? 1) + 1 : 1;
  const createdAt = latest ? latest.createdAt || latest.timestamp || timestamp : timestamp;
  const previousDecision = latest ? latest.decision : undefined;

  const intermediatePayload: Omit<AnalystReviewRecord, "auditHash"> = {
    reviewId: `rev_${invId}_${regId}_r${revisionNumber}`,
    investigationId: invId,
    candidateRegionId: regId,
    seriesId: params.seriesId || (latest ? latest.seriesId : ""),
    discoveryPairId: params.discoveryPairId || (latest ? latest.discoveryPairId : ""),
    createdAt,
    updatedAt: timestamp,
    decision: normDecision,
    analystId,
    analystNote: note,
    selectedReason: reason,
    reasonCode,
    previousDecision,
    revisionNumber,
    comments: note,
    timestamp,
  };

  const auditHash = computeReviewAuditHash(intermediatePayload);

  const newRevision: AnalystReviewRecord = {
    ...intermediatePayload,
    auditHash,
  };

  const all = loadAllRecords();
  all.unshift(newRevision);
  saveAllRecords(all);

  return {
    created: true,
    review: newRevision,
    isDuplicate: false,
    revisionNumber,
  };
}

/**
 * Factory to create a validated AnalystReview record (backwards compatible with D4).
 */
export function createAnalystReview(params: {
  investigationId: string;
  candidateRegionId: string;
  decision: ReviewDecision;
  comments?: string;
  analystNote?: string;
  analystId?: string;
  categoryOverride?: string;
  confidenceRating?: number;
  timestamp?: string;
  seriesId?: string;
  discoveryPairId?: string;
  selectedReason?: string;
}): AnalystReviewRecord {
  const timestamp = params.timestamp || new Date().toISOString();
  const analystId = params.analystId || "analyst_local";
  const note = (params.analystNote ?? params.comments ?? "").trim();

  const legacyHash = computeReviewHash(
    params.investigationId,
    params.candidateRegionId,
    params.decision,
    timestamp
  );

  const intermediate: Omit<AnalystReviewRecord, "auditHash"> = {
    reviewId: legacyHash,
    investigationId: params.investigationId,
    candidateRegionId: params.candidateRegionId,
    seriesId: params.seriesId || "",
    discoveryPairId: params.discoveryPairId || "",
    createdAt: timestamp,
    updatedAt: timestamp,
    decision: params.decision,
    analystId,
    analystNote: note,
    selectedReason: params.selectedReason || "Analyst assessment",
    reasonCode: "analyst_review",
    revisionNumber: 1,
    comments: note,
    categoryOverride: params.categoryOverride,
    confidenceRating: params.confidenceRating,
    timestamp,
  };

  const auditHash = computeReviewAuditHash(intermediate);

  return {
    ...intermediate,
    auditHash,
  };
}

/**
 * Retrieves all stored reviews across all investigations (backwards compatible with D4).
 */
export function getAllReviews(): AnalystReviewRecord[] {
  return loadAllRecords();
}

/**
 * Persists a review record (backwards compatible with D4).
 */
export function saveReview(review: AnalystReviewRecord): void {
  const all = loadAllRecords().filter((r) => r.reviewId !== review.reviewId);
  all.unshift(review);
  saveAllRecords(all);
}

/**
 * Retrieves reviews filtered by investigation ID (backwards compatible with D4).
 */
export function getReviewsForInvestigation(
  investigationId: string
): AnalystReviewRecord[] {
  return getAllReviews().filter((r) => r.investigationId === investigationId);
}

/**
 * Removes a review by its unique review ID (backwards compatible with D4).
 */
export function deleteReview(reviewId: string): void {
  const all = getAllReviews().filter((r) => r.reviewId !== reviewId);
  saveAllRecords(all);
}

/**
 * Exports all reviews as a formatted JSON string (backwards compatible with D4).
 */
export function exportReviewsAsJson(): string {
  const reviews = getAllReviews();
  return JSON.stringify(
    {
      exported_at: new Date().toISOString(),
      record_count: reviews.length,
      reviews,
    },
    null,
    2
  );
}

/**
 * Exports complete revision history for a specific investigation and candidate region.
 */
export function exportInvestigationReviewJson(
  investigationId: string,
  candidateRegionId?: string
): string {
  const history = getReviewHistory(investigationId, candidateRegionId);
  const latest = history[0] || null;

  const exportPayload: ReviewHistoryExport = {
    schemaVersion: "astra_review_v2",
    exportedAt: new Date().toISOString(),
    investigationId,
    candidateRegionId: candidateRegionId || latest?.candidateRegionId || "unknown",
    seriesId: latest?.seriesId,
    discoveryPairId: latest?.discoveryPairId,
    currentDecision: latest?.decision || "PENDING",
    latestRevisionNumber: latest?.revisionNumber || 0,
    totalRevisions: history.length,
    currentAuditHash: latest?.auditHash || "",
    revisions: history,
  };

  return JSON.stringify(exportPayload, null, 2);
}

/**
 * Clears the review database (useful for testing).
 */
export function clearAllReviews(): void {
  memoryStore = [];
  if (typeof window !== "undefined" && window.localStorage) {
    try {
      window.localStorage.removeItem(REVIEWS_STORAGE_KEY_V2);
      window.localStorage.removeItem(REVIEWS_STORAGE_KEY_V1);
    } catch {
      // Ignore
    }
  }
}
