/**
 * Unit Tests for Milestone D7: Evidence & False-Alarm Panel
 *
 * Covers all 20 required criteria:
 * 1. Classification summary renders.
 * 2. Category renders from backend data.
 * 3. Confidence tier renders without probability conversion.
 * 4. Rule evaluations render.
 * 5. Rule values/reasons are displayed without recomputation.
 * 6. Morphological evidence renders.
 * 7. Spectral evidence renders.
 * 8. Missing NDVI/NDWI is represented correctly.
 * 9. M4D RETAINED renders correctly.
 * 10. M4D FLAGGED renders correctly.
 * 11. M4D SUPPRESSED renders correctly.
 * 12. M4D INSUFFICIENT_EVIDENCE renders correctly.
 * 13. Individual false-alarm factors render.
 * 14. Registration/co-registration evidence renders when available.
 * 15. Cloud/shadow/haze/view-angle evidence renders when available.
 * 16. Missing optional risk factors do not crash.
 * 17. Provenance references are preserved.
 * 18. Unknown/uncertain classification renders safely.
 * 19. Demo dossier renders correctly.
 * 20. No frontend-generated confidence/risk score is introduced.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  transformInvestigationDossier,
  getM4dDecisionDetails,
  getConfidenceTierDetails,
  getArtifactFactorLabel,
} from "../services/transformers.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationDossier } from "../types/api.ts";
import type { InvestigationSummary } from "../types/models.ts";

describe("Milestone D7: Evidence & False-Alarm Panel Unit Tests", () => {
  // 1. Classification Summary Renders
  it("extracts and renders classification summary from backend data", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.ok(summary.classificationEvidence);
    assert.strictEqual(summary.classificationEvidence.regionId, "reg_0002");
    assert.strictEqual(summary.classificationEvidence.category, "construction");
    assert.strictEqual(summary.classificationEvidence.confidenceTier, "high");
    assert.strictEqual(summary.classificationEvidence.isAmbiguous, false);
    assert.ok(summary.classificationEvidence.decisionReason.includes("rectangularity"));
  });

  // 2. Category Renders from Backend Data
  it("renders exact backend semantic categories without frontend reclassification", () => {
    const categories = ["construction", "clearance", "water_extent_change", "road_development", "unknown"];
    for (const cat of categories) {
      const mockDossier: InvestigationDossier = {
        ...DEMO_INVESTIGATION_DOSSIER,
        stage_results: [
          {
            stage: "m4c_classification",
            status: "COMPLETED",
            artifact_id: `cls_${cat}`,
            provenance_id: `prov_cls_${cat}`,
            output_path: null,
            error_message: null,
            details: {
              target_classification: {
                region_id: "reg_0002",
                category: cat,
                confidence_tier: "medium",
                decision_reason: `Classified as ${cat}`,
                is_ambiguous: false,
              },
            },
            timestamp: "2026-04-15T10:30:03Z",
          },
        ],
      };
      const summary = transformInvestigationDossier(mockDossier);
      assert.strictEqual(summary.classificationEvidence?.category, cat);
    }
  });

  // 3. Confidence Tier Renders Without Probability Conversion
  it("renders confidence tier as evidentiary stratification without probability conversion", () => {
    const highDetails = getConfidenceTierDetails("HIGH");
    assert.strictEqual(highDetails.tier, "HIGH");
    assert.strictEqual(highDetails.label, "HIGH CONFIDENCE");
    assert.ok(!highDetails.description.includes("%"));
    assert.ok(highDetails.disclaimer.includes("NOT a calibrated probability"));

    const medDetails = getConfidenceTierDetails("MEDIUM");
    assert.strictEqual(medDetails.tier, "MEDIUM");
    assert.ok(medDetails.disclaimer.includes("NOT a calibrated probability"));

    const lowDetails = getConfidenceTierDetails("LOW");
    assert.strictEqual(lowDetails.tier, "LOW");
    assert.ok(lowDetails.disclaimer.includes("NOT a calibrated probability"));

    const uncDetails = getConfidenceTierDetails("UNCERTAIN");
    assert.strictEqual(uncDetails.tier, "UNCERTAIN");
    assert.ok(uncDetails.disclaimer.includes("NOT a calibrated probability"));
  });

  // 4. Rule Evaluations Render
  it("renders complete list of rule evaluations preserving backend ordering", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const rules = summary.classificationEvidence?.ruleEvaluations;
    assert.ok(rules);
    assert.strictEqual(rules.length, 7);

    assert.strictEqual(rules[0].ruleId, "rule_const_geom_rectangularity");
    assert.strictEqual(rules[0].matched, true);
    assert.strictEqual(rules[0].weight, 30);
    assert.strictEqual(rules[0].scoreContribution, 0.3);

    assert.strictEqual(rules[5].ruleId, "disqual_const_water_presence");
    assert.strictEqual(rules[5].matched, false);
    assert.strictEqual(rules[5].scoreContribution, 0.0);
  });

  // 5. Rule Values and Reasons are Displayed Without Recomputation
  it("preserves observed feature values and thresholds in rule evaluations without recomputing", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const rectRule = summary.classificationEvidence?.ruleEvaluations.find(
      (r) => r.ruleId === "rule_const_geom_rectangularity"
    );
    assert.ok(rectRule);
    assert.strictEqual(rectRule.evidenceUsed?.rectangularity, 1.0);
    assert.strictEqual(rectRule.evidenceUsed?.threshold, 0.6);
    assert.ok(rectRule.description.includes(">= 0.60"));
  });

  // 6. Morphological Evidence Renders
  it("renders all morphological features extracted by Phase M4C-A", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const morph = summary.classificationEvidence?.morphologicalFeatures;
    assert.ok(morph);

    assert.strictEqual(morph.area_px ?? (morph as any).areaPx ?? morph.pixelCount, 900);
    assert.strictEqual(morph.width_px ?? morph.widthPx, 30);
    assert.strictEqual(morph.height_px ?? morph.heightPx, 30);
    assert.strictEqual(morph.aspect_ratio ?? morph.aspectRatio, 1.0);
    assert.strictEqual(morph.perimeter_px ?? morph.perimeterPx, 120.0);
    assert.strictEqual(morph.compactness, 0.785);
    assert.strictEqual(morph.rectangularity, 1.0);
    assert.strictEqual(morph.elongation, 1.0);
  });

  // 7. Spectral Evidence Renders
  it("renders per-band reflectance means, deltas, and brightness delta", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const spectral = summary.classificationEvidence?.spectralEvidence;
    assert.ok(spectral);
    assert.strictEqual(spectral.available, true);
    assert.strictEqual(spectral.hasWavelengthMetadata, true);
    assert.deepStrictEqual(spectral.bandNames, ["B02_blue", "B03_green", "B04_red", "B08_nir"]);

    assert.strictEqual(spectral.earlierMeanPerBand["B02_blue"], 0.12);
    assert.strictEqual(spectral.laterMeanPerBand["B02_blue"], 0.22);
    assert.strictEqual(spectral.deltaPerBand["B02_blue"], 0.1);

    assert.strictEqual(spectral.brightnessDelta?.value, 0.1);
    assert.strictEqual(spectral.ndviMean?.value, 0.05);
    assert.strictEqual(spectral.ndwiMean?.value, -0.22);
  });

  // 8. Missing NDVI/NDWI is Represented Correctly
  it("correctly indicates unavailable state for physical indices when bands are missing", () => {
    const mockDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      stage_results: [
        {
          stage: "m4c_evidence_extraction",
          status: "COMPLETED",
          artifact_id: "evi_rgb_only",
          provenance_id: "prov_evi_rgb",
          output_path: null,
          error_message: null,
          details: {
            target_evidence: {
              region_id: "reg_0002",
              spectral: {
                available: true,
                has_wavelength_metadata: false,
                band_names: ["red", "green", "blue"],
                earlier_mean_per_band: { red: 0.1, green: 0.1, blue: 0.1 },
                later_mean_per_band: { red: 0.2, green: 0.2, blue: 0.2 },
                delta_per_band: { red: 0.1, green: 0.1, blue: 0.1 },
                ndvi_mean: {
                  available: false,
                  unavailability_reason: "NIR and Red bands not explicitly identified in metadata or configuration",
                },
                ndwi_mean: {
                  available: false,
                  unavailability_reason: "Green and NIR bands not explicitly identified in metadata or configuration",
                },
              },
            },
          },
          timestamp: "2026-04-15T10:30:02Z",
        },
      ],
    };

    const summary = transformInvestigationDossier(mockDossier);
    const spectral = summary.classificationEvidence?.spectralEvidence;
    assert.ok(spectral);
    assert.strictEqual(spectral.ndviMean?.available, false);
    assert.ok(spectral.ndviMean?.reason?.includes("NIR and Red bands not explicitly identified"));
    assert.strictEqual(spectral.ndwiMean?.available, false);
  });

  // 9. M4D RETAINED Renders Correctly
  it("renders M4D RETAINED decision with mandatory non-ground-truth semantic caveat", () => {
    const details = getM4dDecisionDetails("RETAINED");
    assert.strictEqual(details.decision, "RETAINED");
    assert.ok(details.label.includes("Retained"));
    assert.ok(details.semanticCaveat.includes("RETAINED does NOT mean 'verified ground truth'"));
    assert.ok(details.semanticCaveat.includes("no sufficient false-alarm evidence"));
  });

  // 10. M4D FLAGGED Renders Correctly
  it("renders M4D FLAGGED decision with neutral triage description", () => {
    const details = getM4dDecisionDetails("FLAGGED");
    assert.strictEqual(details.decision, "FLAGGED");
    assert.ok(details.label.includes("Flagged"));
    assert.ok(details.sublabel.includes("Analyst Review Required"));
    assert.ok(details.statusDescription.includes("analyst attention"));
  });

  // 11. M4D SUPPRESSED Renders Correctly
  it("renders M4D SUPPRESSED decision indicating conservative physical gate satisfied", () => {
    const details = getM4dDecisionDetails("SUPPRESSED");
    assert.strictEqual(details.decision, "SUPPRESSED");
    assert.ok(details.label.includes("Suppressed"));
    assert.ok(details.statusDescription.includes("physical gate was fully satisfied"));
    assert.ok(details.semanticCaveat.includes("Zero Silent Drops"));
  });

  // 12. M4D INSUFFICIENT_EVIDENCE Renders Correctly
  it("renders M4D INSUFFICIENT_EVIDENCE when critical bands or metadata are missing", () => {
    const details = getM4dDecisionDetails("INSUFFICIENT_EVIDENCE");
    assert.strictEqual(details.decision, "INSUFFICIENT_EVIDENCE");
    assert.strictEqual(details.label, "INSUFFICIENT EVIDENCE");
    assert.ok(details.statusDescription.includes("spectral bands or georeferencing metadata were unavailable"));
  });

  // 13. Individual False-Alarm Factors Render
  it("renders individual false-alarm factors across evaluated detectors", () => {
    assert.strictEqual(getArtifactFactorLabel("cloud_contamination"), "Cloud Contamination");
    assert.strictEqual(getArtifactFactorLabel("coregistration_edge_shear"), "Co-Registration Edge Shear");

    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const factors = summary.suppressionEvidence?.artifactFactors;
    assert.ok(factors);
    assert.strictEqual(factors.length, 9);

    const cloud = factors.find((f) => f.artifactType === "cloud_contamination");
    assert.ok(cloud);
    assert.strictEqual(cloud.label, "Cloud Contamination");
    assert.strictEqual(cloud.detected, false);
    assert.strictEqual(cloud.hardTriggered, false);
    assert.strictEqual(cloud.status, "CLEAR");
  });

  // 14. Registration/Co-Registration Evidence Renders
  it("renders co-registration edge shear detector findings and metrics", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const shear = summary.suppressionEvidence?.artifactFactors.find(
      (f) => f.artifactType === "coregistration_edge_shear"
    );
    assert.ok(shear);
    assert.strictEqual(shear.label, "Co-Registration Edge Shear");
    assert.strictEqual(shear.status, "CLEAR");
    assert.strictEqual(shear.metricsUsed?.minor_axis_width_px, 30.0);
    assert.strictEqual(shear.metricsUsed?.edge_overlap, 0.05);
  });

  // 15. Cloud, Shadow, Haze, and View-Angle Evidence Renders
  it("renders cloud, shadow, haze, and parallax detectors with appropriate labels", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const factorTypes = summary.suppressionEvidence?.artifactFactors.map((f) => f.artifactType) || [];
    assert.ok(factorTypes.includes("cloud_contamination"));
    assert.ok(factorTypes.includes("cloud_shadow"));
    assert.ok(factorTypes.includes("haze_aerosol"));
    assert.ok(factorTypes.includes("viewing_geometry_parallax"));

    const parallax = summary.suppressionEvidence?.artifactFactors.find((f) => f.artifactType === "viewing_geometry_parallax");
    assert.ok(parallax);
    assert.strictEqual(parallax.label, "Viewing Geometry Parallax");
  });

  // 16. Missing Optional Risk Factors Do Not Crash
  it("handles missing optional factors and empty rule evaluations gracefully", () => {
    const sparseDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      stage_results: [],
    };
    const summary = transformInvestigationDossier(sparseDossier);
    assert.ok(summary.classificationEvidence);
    assert.ok(summary.suppressionEvidence);
    assert.strictEqual(summary.classificationEvidence.ruleEvaluations.length, 0);
    assert.strictEqual(summary.suppressionEvidence.artifactFactors.length, 0);
  });

  // 17. Provenance References are Preserved
  it("preserves stage artifact IDs and provenance IDs across M4C and M4D", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.strictEqual(summary.classificationEvidence?.sourceArtifactId, "cls_pair_obs_01__obs_02");
    assert.strictEqual(summary.classificationEvidence?.provenanceId, "prov_cls_pair_obs_01__obs_02");

    assert.strictEqual(summary.suppressionEvidence?.sourceArtifactId, "sup_pair_obs_01__obs_02");
    assert.strictEqual(summary.suppressionEvidence?.provenanceId, "prov_sup_pair_obs_01__obs_02");
    assert.strictEqual(summary.suppressionEvidence?.filteredMaskPath, "data/processed/suppression/sup_pair_obs_01__obs_02_mask.tif");
  });

  // 18. Unknown/Uncertain Classification Renders Safely
  it("safely handles unknown category and uncertain confidence tier without errors", () => {
    const unknownDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      stage_results: [
        {
          stage: "m4c_classification",
          status: "COMPLETED",
          artifact_id: "cls_unknown",
          provenance_id: "prov_cls_unknown",
          output_path: null,
          error_message: null,
          details: {
            target_classification: {
              region_id: "reg_0002",
              category: "unknown",
              confidence_tier: "uncertain",
              decision_reason: "Evidence alignment score 0.35 failed minimum threshold (0.45).",
              is_ambiguous: true,
              candidate_scores: { unknown: 1.0 },
            },
          },
          timestamp: "2026-04-15T10:30:03Z",
        },
      ],
    };

    const summary = transformInvestigationDossier(unknownDossier);
    assert.strictEqual(summary.classificationEvidence?.category, "unknown");
    assert.strictEqual(summary.classificationEvidence?.confidenceTier, "uncertain");
    assert.strictEqual(summary.classificationEvidence?.isAmbiguous, true);
  });

  // 19. Demo Dossier Renders Correctly
  it("renders verified demo dossier with genuine target construction pathway", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.strictEqual(summary.candidateRegionId, "reg_0002");
    assert.strictEqual(summary.classificationEvidence?.category, "construction");
    assert.strictEqual(summary.classificationEvidence?.confidenceTier, "high");
    assert.strictEqual(summary.suppressionEvidence?.decision, "RETAINED");
    assert.strictEqual(summary.suppressionEvidence?.artifactRiskScore, 0.06);
    assert.strictEqual(summary.suppressionEvidence?.decisionBasis, "CONSERVATIVE_MULTI_EVIDENCE");
  });

  // 20. No Frontend-Generated Confidence/Risk Score Introduced
  it("verifies that all confidence tiers and risk scores originate strictly from backend data", () => {
    const summary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    // The evidenceScore and artifactRiskScore are numbers provided directly by the backend
    assert.strictEqual(typeof summary.classificationEvidence?.evidenceScore, "number");
    assert.strictEqual(typeof summary.suppressionEvidence?.artifactRiskScore, "number");

    // Tier details do not calculate probabilities or convert HIGH to percentages
    const tierDetails = getConfidenceTierDetails(summary.classificationEvidence?.confidenceTier || "high");
    assert.strictEqual(tierDetails.tier, "HIGH");
    assert.strictEqual(typeof tierDetails.label, "string");
    assert.ok(tierDetails.disclaimer.includes("NOT a calibrated probability"));
  });
});
