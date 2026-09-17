/**
 * Unit Tests for Milestone D6: Spatial Candidate Panel
 *
 * Covers all 20 required criteria:
 * 1. Candidate identity renders.
 * 2. Bounding box renders correctly.
 * 3. Centroid renders correctly.
 * 4. Local offline SVG/Canvas footprint renders.
 * 5. Geometry-unavailable state works.
 * 6. EXACT_PIXEL_GRID is displayed correctly.
 * 7. GEOREFERENCED_BBOX is displayed correctly.
 * 8. GEOREFERENCED_CENTROID_ONLY is displayed correctly.
 * 9. DISJOINT is displayed correctly.
 * 10. INSUFFICIENT_METADATA is displayed correctly.
 * 11. MATCHED correspondence renders.
 * 12. AMBIGUOUS correspondence renders.
 * 13. SPLIT/MERGED relationships render without forcing a match.
 * 14. Region IDs changing across epochs are displayed correctly.
 * 15. IoU and centroid drift are displayed when provided.
 * 16. Missing optional metrics do not crash.
 * 17. Change mask preview uses existing API URL/client functionality.
 * 18. Missing change mask is handled.
 * 19. No external map/basemap is required.
 * 20. D4/D5/D6 integration remains compatible.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  transformInvestigationDossier,
  getSpatialStatusDetails,
  getRelationshipDetails,
  formatCoordinatesWgs84,
  formatBoundingBoxWgs84,
  computeSvgFootprint,
} from "../services/transformers.ts";
import { getChangeMaskUrl } from "../services/api.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationDossier } from "../types/api.ts";
import type { InvestigationSummary } from "../types/models.ts";

describe("Milestone D6: Spatial Candidate Panel Unit Tests", () => {
  // 1. Candidate Identity
  it("extracts and renders backend-provided candidate identity accurately", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    assert.strictEqual(summary.candidateRegionId, "reg_0002");
    assert.strictEqual(summary.discoveryPairId, "pair_obs_01__obs_02");
    assert.strictEqual(summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.category.primary, "CONSTRUCTION");
    assert.strictEqual(summary.confidenceTier, "high");
    assert.strictEqual(summary.supportStatus, "STRONG_TEMPORAL_SUPPORT");
    assert.strictEqual(summary.seriesId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");
  });

  // 2. Bounding Box Formatting
  it("formats WGS84 bounding box coordinates clearly and consistently", () => {
    const bbox = {
      minLon: 77.335,
      minLat: 13.085,
      maxLon: 77.345,
      maxLat: 13.095,
    };

    const details = formatBoundingBoxWgs84(bbox);
    assert.ok(details !== null);
    assert.strictEqual(details.minLonFormatted, "77.335000° E");
    assert.strictEqual(details.minLatFormatted, "13.085000° N");
    assert.strictEqual(details.maxLonFormatted, "77.345000° E");
    assert.strictEqual(details.maxLatFormatted, "13.095000° N");
    assert.strictEqual(details.latSpanDeg, 0.01);
    assert.strictEqual(details.lonSpanDeg, 0.01);
  });

  // 3. Centroid Formatting
  it("formats WGS84 centroid coordinates with proper hemisphere indicators", () => {
    const coordEastNorth = formatCoordinatesWgs84(77.34, 13.09);
    assert.strictEqual(coordEastNorth, "13.090000° N, 77.340000° E");

    const coordWestNorth = formatCoordinatesWgs84(-122.4194, 37.7749);
    assert.strictEqual(coordWestNorth, "37.774900° N, 122.419400° W");

    const coordWestSouth = formatCoordinatesWgs84(-70.6693, -33.4489);
    assert.strictEqual(coordWestSouth, "33.448900° S, 70.669300° W");
  });

  // 4. Local Offline SVG Footprint Rendering
  it("computes proportional local offline SVG coordinates for footprint and centroid", () => {
    const bbox = { minLon: 77.335, minLat: 13.085, maxLon: 77.345, maxLat: 13.095 };
    const centroid: [number, number] = [77.34, 13.09]; // Dead center

    const svg = computeSvgFootprint(bbox, centroid, 400, 240, 40);
    assert.ok(svg !== null);
    assert.strictEqual(svg.svgWidth, 400);
    assert.strictEqual(svg.svgHeight, 240);

    // Box dimensions
    assert.strictEqual(svg.box.x, 40);
    assert.strictEqual(svg.box.y, 40);
    assert.strictEqual(svg.box.width, 320);
    assert.strictEqual(svg.box.height, 160);

    // Centroid should be exactly in the center of the box (x: 40 + 160 = 200, y: 40 + 80 = 120)
    assert.strictEqual(svg.centroid.x, 200);
    assert.strictEqual(svg.centroid.y, 120);

    // Labels
    assert.match(svg.labels.west, /77.3350/);
    assert.match(svg.labels.east, /77.3450/);
    assert.match(svg.labels.north, /13.0950/);
    assert.match(svg.labels.south, /13.0850/);
  });

  // 5. Geometry-Unavailable State
  it("handles geometry-unavailable state gracefully without fabricating coordinates", () => {
    assert.strictEqual(formatBoundingBoxWgs84(null), null);
    assert.strictEqual(formatBoundingBoxWgs84(undefined), null);
    assert.strictEqual(computeSvgFootprint(null), null);
    assert.strictEqual(computeSvgFootprint(undefined), null);
    assert.strictEqual(formatCoordinatesWgs84(null, null), "Coordinates unavailable");
    assert.strictEqual(formatCoordinatesWgs84(undefined, undefined), "Coordinates unavailable");
  });

  // 6. EXACT_PIXEL_GRID Status
  it("displays EXACT_PIXEL_GRID correctly with compatible status", () => {
    const details = getSpatialStatusDetails("EXACT_PIXEL_GRID");
    assert.strictEqual(details.status, "EXACT_PIXEL_GRID");
    assert.strictEqual(details.label, "Exact Pixel Grid");
    assert.strictEqual(details.isCompatible, true);
    assert.strictEqual(details.icon, "🎯");
    assert.match(details.description, /pixel grid/i);
  });

  // 7. GEOREFERENCED_BBOX Status
  it("displays GEOREFERENCED_BBOX correctly with compatible status", () => {
    const details = getSpatialStatusDetails("GEOREFERENCED_BBOX");
    assert.strictEqual(details.status, "GEOREFERENCED_BBOX");
    assert.strictEqual(details.label, "Georeferenced Bounding Box");
    assert.strictEqual(details.isCompatible, true);
    assert.strictEqual(details.icon, "📐");
    assert.match(details.description, /bounding box/i);
  });

  // 8. GEOREFERENCED_CENTROID_ONLY Status
  it("displays GEOREFERENCED_CENTROID_ONLY correctly", () => {
    const details = getSpatialStatusDetails("GEOREFERENCED_CENTROID_ONLY");
    assert.strictEqual(details.status, "GEOREFERENCED_CENTROID_ONLY");
    assert.strictEqual(details.label, "Centroid Proximity Only");
    assert.strictEqual(details.isCompatible, true);
    assert.strictEqual(details.icon, "📍");
    assert.match(details.description, /centroid/i);
  });

  // 9. DISJOINT Status
  it("displays DISJOINT correctly as incompatible spatial outcome", () => {
    const details = getSpatialStatusDetails("DISJOINT");
    assert.strictEqual(details.status, "DISJOINT");
    assert.strictEqual(details.label, "Disjoint Footprint");
    assert.strictEqual(details.isCompatible, false);
    assert.strictEqual(details.icon, "❌");
    assert.match(details.description, /not overlap/i);
  });

  // 10. INSUFFICIENT_METADATA Status
  it("displays INSUFFICIENT_METADATA correctly as incompatible spatial outcome", () => {
    const details = getSpatialStatusDetails("INSUFFICIENT_METADATA");
    assert.strictEqual(details.status, "INSUFFICIENT_METADATA");
    assert.strictEqual(details.label, "Insufficient Spatial Metadata");
    assert.strictEqual(details.isCompatible, false);
    assert.strictEqual(details.icon, "❓");
    assert.match(details.description, /missing/i);
  });

  // 11. MATCHED Relationship
  it("displays MATCHED relationship correctly as confirmed target match", () => {
    const details = getRelationshipDetails("MATCHED");
    assert.strictEqual(details.relationship, "MATCHED");
    assert.strictEqual(details.label, "Matched Target");
    assert.strictEqual(details.isMatched, true);
    assert.strictEqual(details.icon, "✓");
  });

  // 12. AMBIGUOUS Relationship
  it("displays AMBIGUOUS relationship without assuming match", () => {
    const details = getRelationshipDetails("AMBIGUOUS");
    assert.strictEqual(details.relationship, "AMBIGUOUS");
    assert.strictEqual(details.label, "Ambiguous Correspondence");
    assert.strictEqual(details.isMatched, false);
    assert.strictEqual(details.icon, "⚠️");
  });

  // 13. SPLIT and MERGED Relationships
  it("displays SPLIT and MERGED relationships without forcing a match", () => {
    const splitDetails = getRelationshipDetails("SPLIT");
    assert.strictEqual(splitDetails.relationship, "SPLIT");
    assert.strictEqual(splitDetails.label, "Split Target");
    assert.strictEqual(splitDetails.isMatched, false);
    assert.strictEqual(splitDetails.icon, "🔀");

    const mergedDetails = getRelationshipDetails("MERGED");
    assert.strictEqual(mergedDetails.relationship, "MERGED");
    assert.strictEqual(mergedDetails.label, "Merged Target");
    assert.strictEqual(mergedDetails.isMatched, false);
    assert.strictEqual(mergedDetails.icon, "🔁");
  });

  // 14. Region IDs Changing Across Epochs
  it("correctly tracks candidate region ID shifts across independent epochs", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const epochs = summary.spatialCorrespondence.epochs;

    assert.strictEqual(epochs.length, 3);

    // Epoch 1 (T1/T2): reg_0002 -> reg_0002
    assert.strictEqual(epochs[0].referenceCandidateId, "reg_0002");
    assert.strictEqual(epochs[0].matchedRegionId, "reg_0002");
    assert.strictEqual(epochs[0].isIdShifted, false);

    // Epoch 2 (T1/T3): reg_0002 -> reg_0001
    assert.strictEqual(epochs[1].referenceCandidateId, "reg_0002");
    assert.strictEqual(epochs[1].matchedRegionId, "reg_0001");
    assert.strictEqual(epochs[1].isIdShifted, true);

    // Epoch 3 (T1/T4): reg_0002 -> reg_0003
    assert.strictEqual(epochs[2].referenceCandidateId, "reg_0002");
    assert.strictEqual(epochs[2].matchedRegionId, "reg_0003");
    assert.strictEqual(epochs[2].isIdShifted, true);
  });

  // 15. IoU and Centroid Drift Metrics
  it("extracts and displays metric IoU and centroid drift in meters", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const epochs = summary.spatialCorrespondence.epochs;

    // Epoch 1
    assert.strictEqual(epochs[0].metricIou, 1.0);
    assert.strictEqual(epochs[0].centroidDistanceM, 0.0);

    // Epoch 2
    assert.strictEqual(epochs[1].metricIou, 0.88);
    assert.strictEqual(epochs[1].centroidDistanceM, 4.2);

    // Epoch 3
    assert.strictEqual(epochs[2].metricIou, 0.85);
    assert.strictEqual(epochs[2].centroidDistanceM, 4.8);
  });

  // 16. Missing Optional Metrics
  it("handles missing optional metrics safely without runtime exceptions", () => {
    const sparseDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      lineage: {
        ...DEMO_INVESTIGATION_DOSSIER.lineage,
        candidate_correspondence: {
          pair_sparse: {
            reference_candidate_id: "reg_0002",
            target_pair_id: "pair_sparse",
            status: "INSUFFICIENT_METADATA",
            relationship: "NONE",
            matched_region_id: null,
            metric_iou: undefined,
            centroid_distance_m: undefined,
          },
        },
      },
    };

    const summary = transformInvestigationDossier(sparseDossier);
    assert.strictEqual(summary.spatialCorrespondence.epochs.length, 1);
    const ep = summary.spatialCorrespondence.epochs[0];
    assert.strictEqual(ep.matchedRegionId, undefined);
    assert.strictEqual(ep.metricIou, 0.0);
    assert.strictEqual(ep.centroidDistanceM, 0.0);
    assert.strictEqual(ep.relationship, "NONE");
  });

  // 17. Change Mask Preview URL
  it("constructs deterministic change mask image URL from API client", () => {
    const url = getChangeMaskUrl("cdr_pair_obs_01__obs_02");
    assert.match(url, /\/api\/v1\/change-detection\/cdr_pair_obs_01__obs_02\/mask/);
  });

  // 18. Missing Change Mask Handled
  it("handles missing change mask result ID without throwing", () => {
    const summary = transformInvestigationDossier({
      ...DEMO_INVESTIGATION_DOSSIER,
      lineage: {
        ...DEMO_INVESTIGATION_DOSSIER.lineage,
        change_detection_result_ids: [],
      },
    });

    assert.strictEqual(summary.changeMaskResultId, undefined);
  });

  // 19. No External Map Required (Offline Air-Gapped)
  it("verifies offline SVG footprint calculations require no remote resources", () => {
    const bbox = { minLon: 77.335, minLat: 13.085, maxLon: 77.345, maxLat: 13.095 };
    const centroid: [number, number] = [77.34, 13.09];
    const svg = computeSvgFootprint(bbox, centroid);

    assert.ok(svg !== null);
    assert.ok(typeof svg.box.width === "number");
    assert.ok(typeof svg.box.height === "number");
    assert.ok(typeof svg.centroid.x === "number");
    assert.ok(typeof svg.centroid.y === "number");
    // No URLs, no third-party APIs
    assert.ok(!("tileUrl" in svg));
  });

  // 20. D4/D5/D6 Integration Compatibility
  it("maintains full compatibility across D4, D5, and D6 data structures", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    // D4 fields
    assert.strictEqual(summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.onset.physicalInterval, "(2026-01-15, 2026-02-15]");

    // D5 fields
    assert.strictEqual(summary.timelineNodes.length, 4);
    assert.strictEqual(summary.timelineNodes[1].status, "EARLIEST_SUPPORTING");

    // D6 fields
    assert.strictEqual(summary.spatialCorrespondence.epochs.length, 3);
    assert.strictEqual(summary.candidateFootprint?.regionId, "reg_0002");
    assert.strictEqual(summary.candidateFootprint?.bboxWgs84?.minLon, 77.335);
    assert.strictEqual(summary.candidateFootprint?.features?.aspect_ratio, 1.0);
    assert.strictEqual(summary.changeMaskResultId, "cdr_pair_obs_01__obs_02");
  });
});
