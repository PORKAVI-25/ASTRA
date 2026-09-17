/**
 * ASTRA Strongly Typed Backend API Client
 *
 * Interacts with ASTRA Backend REST API endpoints (v1).
 * Strictly adheres to ASTRA Offline Policy (Rule 1 & Rule 2).
 * Authoritative reference: docs/dashboard-contract.md
 */

import type {
  ApiErrorDetail,
  ChangeDetectionResult,
  ChangeDetectionRunRequest,
  HealthResponse,
  InvestigationDossier,
  InvestigationRequest,
  TemporalSeries,
  TemporalSeriesPairsResponse,
} from "../types/api";

const API_BASE_URL =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) ||
  "http://127.0.0.1:8000";

/**
 * Custom error class capturing structured backend error envelopes.
 */
export class ApiError extends Error {
  public readonly status: number;
  public readonly errorCode: string;
  public readonly stage?: string;
  public readonly details: Record<string, unknown>;

  constructor(status: number, message: string, errorCode: string = "UNKNOWN_ERROR", stage?: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = errorCode;
    this.stage = stage;
    this.details = details;
  }
}

/**
 * Internal helper to parse and dispatch HTTP responses with structured error decoding.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.json() as Promise<T>;
  }

  let errorPayload: ApiErrorDetail | null = null;
  let rawText = "";

  try {
    const json = await response.json();
    if (json && typeof json === "object") {
      if (json.detail && typeof json.detail === "object") {
        errorPayload = json.detail as ApiErrorDetail;
      } else if (typeof json.detail === "string") {
        errorPayload = {
          error: "ERROR",
          message: json.detail,
          details: {},
        };
      } else if (json.message) {
        errorPayload = json as ApiErrorDetail;
      }
    }
  } catch {
    try {
      rawText = await response.text();
    } catch {
      // Ignored
    }
  }

  const status = response.status;
  const errorCode = errorPayload?.error || `HTTP_${status}`;
  const message =
    errorPayload?.message ||
    rawText ||
    `API request failed with status code ${status}`;
  const stage = errorPayload?.stage;
  const details = errorPayload?.details || {};

  throw new ApiError(status, message, errorCode, stage, details);
}

/**
 * 1. Health & Diagnostics
 * GET /api/v1/health
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return handleResponse<HealthResponse>(response);
}

/**
 * 2. List Available Temporal Series
 * GET /api/v1/temporal/series
 */
export async function fetchSeriesList(): Promise<TemporalSeries[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/temporal/series`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return handleResponse<TemporalSeries[]>(response);
}

/**
 * 3. Retrieve Single Temporal Series by ID
 * GET /api/v1/temporal/series/{series_id}
 */
export async function fetchSeriesById(seriesId: string): Promise<TemporalSeries> {
  const encodedId = encodeURIComponent(seriesId);
  const response = await fetch(`${API_BASE_URL}/api/v1/temporal/series/${encodedId}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return handleResponse<TemporalSeries>(response);
}

/**
 * 4. Generate Pairs for Temporal Series
 * GET /api/v1/temporal/series/{series_id}/pairs?mode={baseline|adjacent|all_pairwise}
 */
export async function fetchSeriesPairs(
  seriesId: string,
  mode: "baseline" | "adjacent" | "all_pairwise" = "baseline"
): Promise<TemporalSeriesPairsResponse> {
  const encodedId = encodeURIComponent(seriesId);
  const response = await fetch(
    `${API_BASE_URL}/api/v1/temporal/series/${encodedId}/pairs?mode=${encodeURIComponent(mode)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    }
  );
  return handleResponse<TemporalSeriesPairsResponse>(response);
}

/**
 * 5. Execute End-to-End Pipeline Investigation
 * POST /api/v1/pipeline/investigate
 */
export async function executeInvestigation(
  request: InvestigationRequest
): Promise<InvestigationDossier> {
  const response = await fetch(`${API_BASE_URL}/api/v1/pipeline/investigate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
  });
  return handleResponse<InvestigationDossier>(response);
}

/**
 * 6. Run M4B Change Detection (Candidate Discovery)
 * POST /api/v1/change-detection/run
 */
export async function runChangeDetection(
  request: ChangeDetectionRunRequest
): Promise<ChangeDetectionResult> {
  const response = await fetch(`${API_BASE_URL}/api/v1/change-detection/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
  });
  return handleResponse<ChangeDetectionResult>(response);
}

/**
 * 7. Retrieve Change Detection Result by ID
 * GET /api/v1/change-detection/{result_id}
 */
export async function fetchChangeDetectionResult(
  resultId: string
): Promise<ChangeDetectionResult> {
  const encodedId = encodeURIComponent(resultId);
  const response = await fetch(`${API_BASE_URL}/api/v1/change-detection/${encodedId}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return handleResponse<ChangeDetectionResult>(response);
}

/**
 * 8. Construct Binary Change Mask Image URL
 * GET /api/v1/change-detection/{result_id}/mask
 */
export function getChangeMaskUrl(resultId: string): string {
  const encodedId = encodeURIComponent(resultId);
  return `${API_BASE_URL}/api/v1/change-detection/${encodedId}/mask`;
}

/**
 * Direct accessor to the active API base URL.
 */
export function getApiBaseUrl(): string {
  return API_BASE_URL;
}
