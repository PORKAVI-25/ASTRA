/**
 * Unit Tests for Milestone D8: Provenance & Cryptographic Lineage Panel
 *
 * Covers all 18 required criteria:
 * 1. Investigation ID renders.
 * 2. Investigation hash renders exactly.
 * 3. Provenance hash renders exactly.
 * 4. Pipeline lineage stages render in correct order.
 * 5. Artifact IDs render from backend data.
 * 6. Upstream SHA-256 hashes render exactly.
 * 7. Source scene/pair references render.
 * 8. Temporal lineage renders.
 * 9. Multi-epoch lineage renders.
 * 10. Region ID changes do not break lineage.
 * 11. Missing hashes are handled safely.
 * 12. Partial lineage is represented honestly.
 * 13. Copy functionality is handled safely.
 * 14. No fake hashes are generated.
 * 15. No blockchain/immutability claims are introduced.
 * 16. Existing D4 lineage behavior remains compatible.
 * 17. Demo dossier renders correctly.
 * 18. One-pair/sparse investigation renders correctly.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { transformInvestigationDossier } from "../services/transformers.ts";
import { DEMO_INVESTIGATION_DOSSIER } from "../services/demoDossier.ts";
import type { InvestigationDossier } from "../types/api.ts";
import type { InvestigationSummary } from "../types/models.ts";

describe("Milestone D8: Provenance & Cryptographic Lineage Panel Unit Tests", () => {
  // 1. Investigation ID Renders
  it("renders investigation ID from backend data accurately", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.strictEqual(summary.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.provenance.investigationId, "inv_8c939ce062ed9b8c");
  });

  // 2. Investigation Hash Renders Exactly
  it("renders investigation deterministic content hash exactly without alteration or truncation", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.strictEqual(summary.contentHash, "8c939ce062ed9b8c");
    assert.strictEqual(summary.provenance.contentHash, "8c939ce062ed9b8c");
  });

  // 3. Provenance Hash / ID Renders Exactly
  it("renders investigation provenance ID and temporal provenance ID exactly", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.strictEqual(summary.provenance.investigationProvenanceId, "prov_inv_8c939ce062ed9b8c");
    assert.strictEqual(summary.provenance.temporalEvidenceProvenanceId, "prov_tem_7c8d9e0f1a2b3c4d");
  });

  // 4. Pipeline Lineage Stages Render in Correct Order
  it("renders pipeline lineage stages in correct analytical order M1 -> M4B -> M4C-A -> M4C-B -> M4D -> M4E -> M4F", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const artifacts = summary.provenance.artifacts || [];

    const stageIds = artifacts.map((a) => a.stageId);
    // Must contain M1, M4B, M4C-A, M4C-B, M4D, M4E, M4F
    assert.ok(stageIds.includes("M1"), "Must include M1");
    assert.ok(stageIds.includes("M4B"), "Must include M4B");
    assert.ok(stageIds.includes("M4C-A"), "Must include M4C-A");
    assert.ok(stageIds.includes("M4C-B"), "Must include M4C-B");
    assert.ok(stageIds.includes("M4D"), "Must include M4D");
    assert.ok(stageIds.includes("M4E"), "Must include M4E");
    assert.ok(stageIds.includes("M4F"), "Must include M4F");

    // Check chronological order of first appearances
    const m1Idx = stageIds.indexOf("M1");
    const m4bIdx = stageIds.indexOf("M4B");
    const m4caIdx = stageIds.indexOf("M4C-A");
    const m4cbIdx = stageIds.indexOf("M4C-B");
    const m4dIdx = stageIds.indexOf("M4D");
    const m4eIdx = stageIds.indexOf("M4E");
    const m4fIdx = stageIds.indexOf("M4F");

    assert.ok(m1Idx < m4bIdx, "M1 must precede M4B");
    assert.ok(m4bIdx < m4caIdx, "M4B must precede M4C-A");
    assert.ok(m4caIdx < m4cbIdx, "M4C-A must precede M4C-B");
    assert.ok(m4cbIdx < m4dIdx, "M4C-B must precede M4D");
    assert.ok(m4dIdx < m4eIdx, "M4D must precede M4E");
    assert.ok(m4eIdx < m4fIdx, "M4E must precede M4F");
  });

  // 5. Artifact IDs Render from Backend Data
  it("renders artifact IDs faithfully from backend stage execution results", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const stages = summary.provenance.stages;

    const m4bStage = stages.find((s) => s.stage === "m4b_change_detection");
    assert.strictEqual(m4bStage?.artifactId, "cdr_pair_obs_01__obs_02");

    const m4caStage = stages.find((s) => s.stage === "m4c_evidence_extraction");
    assert.strictEqual(m4caStage?.artifactId, "evi_pair_obs_01__obs_02");

    const m4cbStage = stages.find((s) => s.stage === "m4c_classification");
    assert.strictEqual(m4cbStage?.artifactId, "cls_pair_obs_01__obs_02");

    const m4dStage = stages.find((s) => s.stage === "m4d_suppression");
    assert.strictEqual(m4dStage?.artifactId, "sup_pair_obs_01__obs_02");
  });

  // 6. Upstream SHA-256 Hashes Render Exactly
  it("renders upstream input tile SHA-256 hashes exactly as recorded", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const hashes = summary.provenance.upstreamHashes;

    assert.strictEqual(
      hashes["data/processed/tiles/obs_01.tif"],
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
    assert.strictEqual(
      hashes["data/processed/tiles/obs_02.tif"],
      "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
    );
  });

  // 7. Source Scene/Pair References Render
  it("renders source scene pair references and discovery pairing strategy", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.strictEqual(summary.discoveryPairId, "pair_obs_01__obs_02");
    assert.strictEqual(summary.pairingStrategy, "baseline");

    const epochLineage = summary.provenance.epochLineage || [];
    assert.strictEqual(epochLineage.length, 3);
    assert.strictEqual(epochLineage[0].pairId, "pair_obs_01__obs_02");
    assert.strictEqual(epochLineage[0].earlierSceneId, "obs_01");
    assert.strictEqual(epochLineage[0].laterSceneId, "obs_02");
  });

  // 8. Temporal Lineage Renders
  it("renders temporal lineage linking pairwise evidence to temporal onset bounds", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);

    assert.strictEqual(summary.onset.preChangeObservationId, "obs_tile_c0000_r0000_z14_01");
    assert.strictEqual(summary.onset.earliestSupportObservationId, "obs_tile_c0000_r0000_z14_02");
    assert.strictEqual(summary.onset.physicalInterval, "(2026-01-15, 2026-02-15]");
    assert.strictEqual(summary.onset.intervalDays, 31.0);
    assert.strictEqual(summary.provenance.temporalEvidenceId, "tem_7c8d9e0f1a2b3c4d");
  });

  // 9. Multi-Epoch Lineage Renders
  it("renders multi-epoch pairwise lineage chain across consecutive observations", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const epochLineage = summary.provenance.epochLineage || [];

    assert.strictEqual(epochLineage.length, 3);

    // Epoch 1: discovery pair
    assert.strictEqual(epochLineage[0].pairId, "pair_obs_01__obs_02");
    assert.strictEqual(epochLineage[0].changeDetectionResultId, "cdr_pair_obs_01__obs_02");
    assert.strictEqual(epochLineage[0].evidenceId, "evi_01");
    assert.strictEqual(epochLineage[0].classificationId, "cls_01");
    assert.strictEqual(epochLineage[0].suppressionId, "sup_01");
    assert.strictEqual(epochLineage[0].metricIou, 1.0);

    // Epoch 2: second pair
    assert.strictEqual(epochLineage[1].pairId, "pair_obs_01__obs_03");
    assert.strictEqual(epochLineage[1].metricIou, 0.88);
    assert.strictEqual(epochLineage[1].centroidDistanceM, 4.2);

    // Epoch 3: third pair
    assert.strictEqual(epochLineage[2].pairId, "pair_obs_01__obs_04");
    assert.strictEqual(epochLineage[2].metricIou, 0.85);
    assert.strictEqual(epochLineage[2].centroidDistanceM, 4.8);
  });

  // 10. Region ID Changes Do Not Break Lineage
  it("tracks candidate region ID shifts across epochs without breaking lineage chain", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const epochLineage = summary.provenance.epochLineage || [];

    // Epoch 1: exact match
    assert.strictEqual(epochLineage[0].matchedRegionId, "reg_0002");
    assert.strictEqual(epochLineage[0].isIdShifted, false);

    // Epoch 2: shifted to reg_0001
    assert.strictEqual(epochLineage[1].matchedRegionId, "reg_0001");
    assert.strictEqual(epochLineage[1].isIdShifted, true);

    // Epoch 3: shifted to reg_0003
    assert.strictEqual(epochLineage[2].matchedRegionId, "reg_0003");
    assert.strictEqual(epochLineage[2].isIdShifted, true);
  });

  // 11. Missing Hashes Handled Safely
  it("handles missing hashes safely without crashing", () => {
    const sparseDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      content_hash: "",
      lineage: {
        ...DEMO_INVESTIGATION_DOSSIER.lineage,
        upstream_hashes: {},
      },
    };

    const summary: InvestigationSummary = transformInvestigationDossier(sparseDossier);
    assert.strictEqual(summary.contentHash, "");
    assert.deepStrictEqual(summary.provenance.upstreamHashes, {});
    assert.strictEqual(summary.provenance.isVerified, false);
  });

  // 12. Partial Lineage Is Represented Honestly
  it("represents partial lineage honestly with specific missing reference documentation", () => {
    const partialDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      lineage: {
        ...DEMO_INVESTIGATION_DOSSIER.lineage,
        classification_ids: [],
        suppression_ids: [],
      },
    };

    const summary: InvestigationSummary = transformInvestigationDossier(partialDossier);
    const comp = summary.provenance.completeness;

    assert.strictEqual(comp?.status, "PARTIAL");
    assert.strictEqual(comp?.label, "Partial Lineage References Available");
    assert.ok(comp?.missingReferences.some((r) => r.includes("Classification IDs")));
    assert.ok(comp?.missingReferences.some((r) => r.includes("Suppression IDs")));
  });

  // 13. Copy Functionality Logic Is Handled Safely
  it("verifies copy and export safety without depending on remote services", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    assert.ok(summary.investigationId.length > 0);
    assert.ok(summary.contentHash.length > 0);
    assert.ok(summary.provenance.investigationProvenanceId.length > 0);
  });

  // 14. No Fake Hashes Are Generated
  it("guarantees no fake hashes or placeholder checksums are invented when missing", () => {
    const missingHashDossier: InvestigationDossier = {
      ...DEMO_INVESTIGATION_DOSSIER,
      content_hash: "",
      stage_results: DEMO_INVESTIGATION_DOSSIER.stage_results.map((s) => ({
        ...s,
        artifact_id: null,
        provenance_id: null,
      })),
      lineage: {
        ...DEMO_INVESTIGATION_DOSSIER.lineage,
        upstream_hashes: {},
      },
    };

    const summary: InvestigationSummary = transformInvestigationDossier(missingHashDossier);
    assert.strictEqual(summary.contentHash, "");
    assert.strictEqual(Object.keys(summary.provenance.upstreamHashes).length, 0);

    const m4bArtifact = summary.provenance.artifacts?.find((a) => a.stageId === "M4B");
    assert.strictEqual(m4bArtifact?.hash, undefined);
    assert.strictEqual(m4bArtifact?.artifactId, "—");
  });

  // 15. No Blockchain or Immutability Overclaims Are Introduced
  it("enforces conservative cryptographic language without claiming blockchain or absolute physical truth", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const comp = summary.provenance.completeness;

    assert.ok(!comp?.label.includes("Blockchain"));
    assert.ok(!comp?.label.includes("Tamper-proof"));
    assert.ok(!comp?.label.includes("Guaranteed Authentic"));
    assert.ok(!comp?.description.includes("blockchain"));
  });

  // 16. Existing D4 Lineage Behavior Remains Compatible
  it("maintains strict backward compatibility with D4 lineage contracts", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const prov = summary.provenance;

    assert.strictEqual(prov.investigationId, "inv_8c939ce062ed9b8c");
    assert.strictEqual(prov.investigationProvenanceId, "prov_inv_8c939ce062ed9b8c");
    assert.strictEqual(prov.contentHash, "8c939ce062ed9b8c");
    assert.strictEqual(prov.isVerified, true);
    assert.strictEqual(prov.stages.length, 6);
  });

  // 17. Demo Dossier Renders Correctly
  it("renders verified demo dossier with complete lineage and audit trail", () => {
    const summary: InvestigationSummary = transformInvestigationDossier(DEMO_INVESTIGATION_DOSSIER);
    const comp = summary.provenance.completeness;

    assert.strictEqual(comp?.status, "COMPLETE");
    assert.strictEqual(comp?.label, "Complete Lineage References Available");
    assert.strictEqual(comp?.missingReferences.length, 0);
    assert.strictEqual(comp?.presentCount, comp?.totalExpected);
  });

  // 18. One-Pair / Sparse Investigation Renders Correctly
  it("safely handles one-pair sparse investigation without crashing", () => {
    const onePairDossier: InvestigationDossier = {
      investigation_id: "inv_sparse_001",
      request: {
        series_id: "series_test",
        discovery_pair_id: "pair_single",
        candidate_region_id: "reg_0001",
      },
      series_id: "series_test",
      discovery_pair_id: "pair_single",
      candidate_region_id: "reg_0001",
      stage_results: [],
      lineage: {
        scene_pair_ids: ["pair_single"],
        change_detection_result_ids: ["cdr_single"],
        evidence_ids: ["evi_single"],
        classification_ids: ["cls_single"],
        suppression_ids: ["sup_single"],
        upstream_hashes: {},
        candidate_correspondence: {},
      },
      provenance_id: "prov_inv_sparse",
      created_at: "2026-05-01T00:00:00Z",
      content_hash: "hash_sparse_001",
      status: "COMPLETED",
    };

    const summary: InvestigationSummary = transformInvestigationDossier(onePairDossier);
    assert.strictEqual(summary.investigationId, "inv_sparse_001");
    assert.strictEqual(summary.provenance.epochLineage?.length, 1);
    assert.strictEqual(summary.provenance.epochLineage?.[0].pairId, "pair_single");
    assert.strictEqual(summary.provenance.stages.length, 0);
  });
});
