/**
 * Unit Tests for Milestone D2: Temporal Series Explorer
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  transformTemporalObservation,
  transformTemporalSeries,
} from "../services/transformers.ts";
import type { TemporalObservation, TemporalSeries } from "../types/api.ts";
import type { TemporalSeriesSummary } from "../types/models.ts";

describe("Milestone D2: Temporal Series Explorer Unit Tests", () => {
  const mockObservationsUnsorted: TemporalObservation[] = [
    {
      observation_id: "obs_03",
      scene_id: "scene_03",
      tile_id: "tile_03",
      acquisition_time: "2026-03-15T10:00:00Z",
      sensor: "Sentinel-2A MSI",
      platform: "Sentinel-2",
      crs: "EPSG:32643",
      bounds_wgs84: { min_lon: 77.30, min_lat: 13.05, max_lon: 77.35, max_lat: 13.10 },
      source_hash: "hash_03_1234567890",
      file_path: "data/tiles/obs_03.png",
      is_synthetic: true,
      metadata: { cloud_cover_percentage: 0.0, valid_pixel_ratio: 1.0 },
    },
    {
      observation_id: "obs_01",
      scene_id: "scene_01",
      tile_id: "tile_01",
      acquisition_time: "2026-01-15T10:00:00Z",
      sensor: "Sentinel-2A MSI",
      platform: "Sentinel-2",
      crs: "EPSG:32643",
      bounds_wgs84: { min_lon: 77.30, min_lat: 13.05, max_lon: 77.35, max_lat: 13.10 },
      source_hash: "hash_01_1234567890",
      file_path: "data/tiles/obs_01.png",
      is_synthetic: true,
      metadata: { cloud_cover_percentage: 0.0, valid_pixel_ratio: 1.0 },
    },
    {
      observation_id: "obs_04",
      scene_id: "scene_04",
      tile_id: "tile_04",
      acquisition_time: "2026-04-15T10:00:00Z",
      sensor: "Sentinel-2A MSI",
      platform: "Sentinel-2",
      crs: "EPSG:32643",
      bounds_wgs84: { min_lon: 77.30, min_lat: 13.05, max_lon: 77.35, max_lat: 13.10 },
      source_hash: "hash_04_1234567890",
      file_path: "data/tiles/obs_04.png",
      is_synthetic: true,
      metadata: { cloud_cover_percentage: 12.5, valid_pixel_ratio: 0.95 },
    },
    {
      observation_id: "obs_02",
      scene_id: "scene_02",
      tile_id: "tile_02",
      acquisition_time: "2026-02-15T10:00:00Z",
      sensor: "Sentinel-2A MSI",
      platform: "Sentinel-2",
      crs: "EPSG:32643",
      bounds_wgs84: { min_lon: 77.30, min_lat: 13.05, max_lon: 77.35, max_lat: 13.10 },
      source_hash: "hash_02_1234567890",
      file_path: "data/tiles/obs_02.png",
      is_synthetic: true,
      metadata: { cloud_cover_percentage: 0.0, valid_pixel_ratio: 1.0 },
    },
  ];

  const mockSeries: TemporalSeries = {
    series_id: "series_grid_lon77.33_lat13.08_c0000_r0000_z14",
    target_id: "grid_lon77.33_lat13.08_c0000_r0000_z14",
    bounds_wgs84: { min_lon: 77.305, min_lat: 13.059, max_lon: 77.353, max_lat: 13.106 },
    observations: mockObservationsUnsorted,
    observation_count: 4,
    earliest_date: "2026-01-15T10:00:00Z",
    latest_date: "2026-04-15T10:00:00Z",
  };

  it("transformTemporalSeries correctly extracts series metadata and AOI extent", () => {
    const summary = transformTemporalSeries(mockSeries);

    assert.strictEqual(summary.seriesId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");
    assert.strictEqual(summary.targetId, "grid_lon77.33_lat13.08_c0000_r0000_z14");
    assert.strictEqual(summary.observationCount, 4);
    assert.match(summary.startDate, /Jan 15, 2026/);
    assert.match(summary.endDate, /Apr 15, 2026/);
    assert.strictEqual(summary.timespanDays, 90.0);
    assert.deepStrictEqual(summary.platforms, ["Sentinel-2"]);
    assert.deepStrictEqual(summary.sensors, ["Sentinel-2A MSI"]);
    assert.ok(summary.boundsWgs84);
    assert.strictEqual(summary.boundsWgs84.minLon, 77.305);
  });

  it("transformTemporalSeries enforces strict chronological observation ordering", () => {
    const summary = transformTemporalSeries(mockSeries);
    const sortedIds = summary.observations.map((o) => o.observationId);

    // Initial input was [obs_03, obs_01, obs_04, obs_02]
    // Expected chronologically sorted: [obs_01, obs_02, obs_03, obs_04]
    assert.deepStrictEqual(sortedIds, ["obs_01", "obs_02", "obs_03", "obs_04"]);

    for (let i = 0; i < summary.observations.length - 1; i++) {
      const t1 = new Date(summary.observations[i].acquisitionTime).getTime();
      const t2 = new Date(summary.observations[i + 1].acquisitionTime).getTime();
      assert.ok(t1 <= t2, `Epoch ${i} must be <= Epoch ${i + 1}`);
    }
  });

  it("transformTemporalObservation preserves observation quality and CRS metadata", () => {
    const rawObs = mockObservationsUnsorted[2]; // obs_04 with cloud 12.5%
    const obs = transformTemporalObservation(rawObs);

    assert.strictEqual(obs.observationId, "obs_04");
    assert.strictEqual(obs.cloudCoverPct, 12.5);
    assert.strictEqual(obs.validPixelRatio, 0.95);
    assert.strictEqual(obs.isSynthetic, true);
    assert.strictEqual(obs.crs, "EPSG:32643");
    assert.strictEqual(obs.sourceHash, "hash_04_1234567890");
  });

  it("handles empty series gracefully with zero observations and zero timespan", () => {
    const emptySeries: TemporalSeries = {
      series_id: "series_empty",
      observations: [],
      observation_count: 0,
    };

    const summary = transformTemporalSeries(emptySeries);
    assert.strictEqual(summary.seriesId, "series_empty");
    assert.strictEqual(summary.observationCount, 0);
    assert.strictEqual(summary.observations.length, 0);
    assert.strictEqual(summary.timespanDays, 0);
    assert.strictEqual(summary.startDate, "N/A");
    assert.strictEqual(summary.endDate, "N/A");
  });

  it("filters series correctly by multi-epoch criteria and search text", () => {
    const series1 = transformTemporalSeries(mockSeries); // 4 epochs
    const series2 = transformTemporalSeries({
      series_id: "series_single_epoch",
      observations: [mockObservationsUnsorted[0]],
      observation_count: 1,
    });

    const catalog: TemporalSeriesSummary[] = [series1, series2];

    // Filter multi-epoch only
    const multiEpochOnly = catalog.filter((s) => s.observationCount >= 2);
    assert.strictEqual(multiEpochOnly.length, 1);
    assert.strictEqual(multiEpochOnly[0].seriesId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");

    // Search query match
    const searchMatch = catalog.filter((s) => s.seriesId.includes("single"));
    assert.strictEqual(searchMatch.length, 1);
    assert.strictEqual(searchMatch[0].seriesId, "series_single_epoch");
  });

  it("series selection state correctly points to target series", () => {
    const series1 = transformTemporalSeries(mockSeries);
    let selectedId: string | null = null;

    // Simulate selecting series
    selectedId = series1.seriesId;
    assert.strictEqual(selectedId, "series_grid_lon77.33_lat13.08_c0000_r0000_z14");

    // Auto-select preferred 4-epoch series
    const catalog = [
      transformTemporalSeries({ series_id: "series_1", observations: [], observation_count: 1 }),
      series1,
    ];
    const autoSelected = catalog.find((s) => s.observationCount >= 4)?.seriesId;
    assert.strictEqual(autoSelected, series1.seriesId);
  });
});
