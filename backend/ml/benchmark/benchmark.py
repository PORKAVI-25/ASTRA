"""Benchmark suite and deterministic dataset generator for satellite embedding models.

Constructs a deterministic synthetic evaluation dataset covering 5 distinct land-cover
classes and coordinates benchmark execution across candidate adapters.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pydantic import BaseModel, Field

from backend.ml.benchmark.candidates import (
    CandidateRegistry,
    EmbeddingModelAdapter,
    registry as default_registry,
)
from backend.ml.benchmark.metrics import (
    compute_latency_statistics,
    compute_retrieval_metrics,
    compute_text_image_retrieval_metrics,
)


class BenchmarkTileItem(BaseModel):
    """Metadata for a benchmark dataset tile."""

    path: str = Field(..., description="Filesystem path to GeoTIFF tile")
    label: str = Field(..., description="Semantic ground truth category label")
    split: str = Field(..., description="'query' or 'gallery'")
    is_synthetic: bool = Field(default=True, description="Strict synthetic data flag")


class BenchmarkDataset:
    """Deterministic synthetic geospatial dataset for reproducible embedding benchmarks.

    Generates 5 semantically distinct land-cover categories:
    1. urban: High spatial frequency grid texture, mixed multi-band reflectance
    2. vegetation: High NIR/Green reflectance, low Red (high synthetic NDVI)
    3. water: High Blue reflectance, near-zero NIR/Red (specular absorption)
    4. roads: High-contrast directional linear geometric infrastructure
    5. cleared: Bare soil signature, elevated Red/SWIR, depressed Green

    Adheres strictly to Rule 9: Flagged as synthetic, never mixed with real operational rasters.
    """

    CATEGORIES = ["urban", "vegetation", "water", "roads", "cleared"]

    TEXT_QUERIES = {
        "urban": "urban built-up area and dense city buildings",
        "vegetation": "green vegetation forest trees and dense canopy",
        "water": "water body lake reservoir river",
        "roads": "roads highway transport network infrastructure",
        "cleared": "cleared bare soil disturbed dry land",
    }

    def __init__(self, root_dir: Union[Path, str]):
        self.root_dir = Path(root_dir)
        self.query_items: List[BenchmarkTileItem] = []
        self.gallery_items: List[BenchmarkTileItem] = []

    def load_real_fixture(self, fixture_dir: Optional[Union[Path, str]] = None) -> bool:
        """Loads locally staged real-world satellite imagery fixture (EuroSAT Sentinel-2)."""
        f_dir = Path(fixture_dir or "data/benchmark/real/eurosat_fixture")
        if not f_dir.exists():
            return False

        self.query_items = []
        self.gallery_items = []

        for category in self.CATEGORIES:
            query_files = sorted(f_dir.glob(f"{category}_query_*.jpg"))
            gallery_files = sorted(f_dir.glob(f"{category}_gallery_*.jpg"))

            for qf in query_files:
                self.query_items.append(
                    BenchmarkTileItem(
                        path=str(qf.as_posix()),
                        label=category,
                        split="query",
                        is_synthetic=False,
                    )
                )

            for gf in gallery_files:
                self.gallery_items.append(
                    BenchmarkTileItem(
                        path=str(gf.as_posix()),
                        label=category,
                        split="gallery",
                        is_synthetic=False,
                    )
                )

        return len(self.query_items) > 0 and len(self.gallery_items) > 0

    def generate(self, width: int = 128, height: int = 128, crs: str = "EPSG:32643") -> None:
        """Generates deterministic GeoTIFF files on disk for all categories."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.query_items = []
        self.gallery_items = []

        west = 750000.0
        north = 1450000.0
        res = 10.0
        transform = from_origin(west, north, res, res)

        for cat_idx, category in enumerate(self.CATEGORIES):
            # Generate 1 query tile and 2 gallery tiles per category
            splits = [("query", 0), ("gallery", 1), ("gallery", 2)]

            for split_name, seed_offset in splits:
                tile_filename = f"{category}_{split_name}_{seed_offset}.tif"
                tile_path = self.root_dir / tile_filename

                # Deterministic pattern generation based on category and seed
                np_rng = np.random.RandomState(seed=cat_idx * 100 + seed_offset + 42)
                data = np.zeros((3, height, width), dtype=np.uint16)

                if category == "urban":
                    # High spatial frequency checkerboard/grid pattern
                    grid = np.zeros((height, width), dtype=np.uint16)
                    for r in range(height):
                        for c in range(width):
                            if (r // 8 + c // 8) % 2 == 0:
                                grid[r, c] = 2200 + np_rng.randint(0, 400)
                            else:
                                grid[r, c] = 800 + np_rng.randint(0, 300)
                    data[0] = grid
                    data[1] = (grid * 0.95).astype(np.uint16)
                    data[2] = (grid * 1.05).astype(np.uint16)

                elif category == "vegetation":
                    # High band 2 (Green) and band 3 (NIR proxy), low band 1 (Red/Blue absorption)
                    base = np_rng.randint(1400, 1800, size=(height, width), dtype=np.uint16)
                    data[0] = (base * 0.25).astype(np.uint16)  # Blue/Red low
                    data[1] = (base * 1.2).astype(np.uint16)   # Green high
                    data[2] = (base * 1.8).astype(np.uint16)   # NIR high

                elif category == "water":
                    # High band 1 (Blue), very low band 2 and near-zero band 3 (NIR absorption)
                    base = np_rng.randint(600, 900, size=(height, width), dtype=np.uint16)
                    data[0] = (base * 1.5).astype(np.uint16)  # Blue
                    data[1] = (base * 0.4).astype(np.uint16)  # Green
                    data[2] = (base * 0.05).astype(np.uint16) # NIR absorbed

                elif category == "roads":
                    # Distinct linear geometric structures (vertical and horizontal cross highways)
                    background = np.full((height, width), 900, dtype=np.uint16)
                    # Cross lines
                    background[height // 2 - 4 : height // 2 + 4, :] = 2800
                    background[:, width // 2 - 4 : width // 2 + 4] = 2800
                    noise = np_rng.randint(0, 150, size=(height, width), dtype=np.uint16)
                    road_data = background + noise
                    data[0] = road_data
                    data[1] = road_data
                    data[2] = road_data

                elif category == "cleared":
                    # Bare soil: high red/brown, moderate blue, low green
                    soil_base = np_rng.randint(1800, 2400, size=(height, width), dtype=np.uint16)
                    data[0] = (soil_base * 0.7).astype(np.uint16)  # Blue
                    data[1] = (soil_base * 0.6).astype(np.uint16)  # Green
                    data[2] = (soil_base * 1.1).astype(np.uint16)  # Red/SWIR high

                # Write georeferenced GeoTIFF
                profile = {
                    "driver": "GTiff",
                    "height": height,
                    "width": width,
                    "count": 3,
                    "dtype": "uint16",
                    "crs": crs,
                    "transform": transform,
                }
                with rasterio.open(tile_path, "w", **profile) as dst:
                    dst.write(data)
                    dst.set_band_description(1, "Band1")
                    dst.set_band_description(2, "Band2")
                    dst.set_band_description(3, "Band3")
                    dst.update_tags(
                        CATEGORY=category,
                        SPLIT=split_name,
                        IS_SYNTHETIC="true",
                        BENCHMARK_SUITE="ASTRA_PHASE2A",
                    )

                item = BenchmarkTileItem(
                    path=str(tile_path.as_posix()),
                    label=category,
                    split=split_name,
                    is_synthetic=True,
                )
                if split_name == "query":
                    self.query_items.append(item)
                else:
                    self.gallery_items.append(item)


class BenchmarkResult(BaseModel):
    """Complete benchmark execution record for an evaluated candidate."""

    candidate_id: str
    candidate_name: str
    family: str
    architecture: str
    embedding_dimension: int
    input_resolution: Tuple[int, int]
    parameter_count_m: Optional[float] = None
    model_size_mb: Optional[float] = None
    license: str
    device: str
    execution_status: str = Field(..., description="'EXECUTED' or 'NOT EXECUTED — dependency/weights unavailable'")
    failure_reason: Optional[str] = None
    offline_compatibility_status: str
    supports_text: bool
    sensor_compatibility: List[str]
    preprocessing_info: str
    reproducibility: str
    notes_limitations: str
    # Performance & Timing (None if not executed)
    inference_latency_ms: Optional[float] = None
    median_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    throughput_fps: Optional[float] = None
    # Retrieval Quality (None if not executed)
    retrieval_metrics: Optional[Dict[str, Any]] = None
    text_retrieval_metrics: Optional[Dict[str, Any]] = None
    dataset_name: str = Field(default="ASTRA Synthetic Dataset", description="Name of evaluation dataset")
    is_synthetic: bool = Field(default=True, description="Strict synthetic data flag")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EmbeddingBenchmarkRunner:
    """Executes the standard satellite representation benchmark suite."""

    def __init__(self, registry: Optional[CandidateRegistry] = None):
        self.registry = registry or default_registry

    def evaluate_candidate(
        self,
        candidate_id: str,
        dataset: BenchmarkDataset,
        device: str = "cpu",
        num_timing_runs: int = 5,
    ) -> BenchmarkResult:
        """Evaluates a single candidate adapter against the benchmark dataset."""
        adapter = self.registry.get(candidate_id)
        if adapter is None:
            raise ValueError(f"Candidate '{candidate_id}' not found in registry")

        meta = adapter.metadata()
        avail, reason = adapter.is_available()

        dataset_is_synthetic = dataset.query_items[0].is_synthetic if dataset.query_items else True
        dataset_name = "ASTRA Synthetic Dataset" if dataset_is_synthetic else "EuroSAT Sentinel-2 Real Fixture"

        # Handle unavailable candidate without fabricating numbers
        if not avail:
            return BenchmarkResult(
                candidate_id=meta.candidate_id,
                candidate_name=meta.display_name,
                family=meta.family,
                architecture=meta.architecture,
                embedding_dimension=meta.embedding_dimension,
                input_resolution=meta.input_resolution,
                parameter_count_m=meta.parameter_count_m,
                model_size_mb=meta.model_size_mb,
                license=meta.license,
                device=device,
                execution_status="NOT EXECUTED — dependency/weights unavailable",
                failure_reason=reason,
                offline_compatibility_status="Full Air-gap Capable once weights are staged locally",
                supports_text=meta.supports_text,
                sensor_compatibility=meta.sensor_compatibility,
                preprocessing_info=meta.preprocessing_info,
                reproducibility=meta.reproducibility_notes,
                notes_limitations=meta.notes,
                dataset_name=dataset_name,
                is_synthetic=dataset_is_synthetic,
            )

        # Candidate is available: execute empirical benchmark
        adapter.load(device=device)

        # 1. Warm-up and latency timing over sample raster
        timing_target = dataset.query_items[0].path
        # Warm-up run
        _ = adapter.encode_image(timing_target)

        latencies_ms: List[float] = []
        for _ in range(num_timing_runs):
            t0 = time.perf_counter()
            _ = adapter.encode_image(timing_target)
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)

        timing_stats = compute_latency_statistics(latencies_ms)

        # 2. Extract query and gallery embeddings
        query_paths = [q.path for q in dataset.query_items]
        query_labels = [q.label for q in dataset.query_items]
        query_embs = adapter.encode_images(query_paths)

        gallery_paths = [g.path for g in dataset.gallery_items]
        gallery_labels = [g.label for g in dataset.gallery_items]
        gallery_embs = adapter.encode_images(gallery_paths)

        # 3. Compute image-to-image retrieval metrics
        retrieval_res = compute_retrieval_metrics(
            query_embeddings=query_embs,
            query_labels=query_labels,
            gallery_embeddings=gallery_embs,
            gallery_labels=gallery_labels,
            top_k_ranks=(1, 3),
        )

        # 4. Compute text-to-image retrieval metrics if supported
        text_res = None
        if meta.supports_text:
            text_queries = [dataset.TEXT_QUERIES[lbl] for lbl in dataset.CATEGORIES]
            text_labels = list(dataset.CATEGORIES)
            text_embs = adapter.encode_texts(text_queries)
            if text_embs is not None:
                text_res = compute_text_image_retrieval_metrics(
                    text_embeddings=text_embs,
                    text_labels=text_labels,
                    image_embeddings=gallery_embs,
                    image_labels=gallery_labels,
                    top_k_ranks=(1, 3),
                )

        return BenchmarkResult(
            candidate_id=meta.candidate_id,
            candidate_name=meta.display_name,
            family=meta.family,
            architecture=meta.architecture,
            embedding_dimension=meta.embedding_dimension,
            input_resolution=meta.input_resolution,
            parameter_count_m=meta.parameter_count_m,
            model_size_mb=meta.model_size_mb,
            license=meta.license,
            device=device,
            execution_status="EXECUTED",
            failure_reason=None,
            offline_compatibility_status="Full Air-gap Capable (staged / built-in)",
            supports_text=meta.supports_text,
            sensor_compatibility=meta.sensor_compatibility,
            preprocessing_info=meta.preprocessing_info,
            reproducibility=meta.reproducibility_notes,
            notes_limitations=meta.notes,
            inference_latency_ms=timing_stats["mean_latency_ms"],
            median_latency_ms=timing_stats["median_latency_ms"],
            p95_latency_ms=timing_stats["p95_latency_ms"],
            throughput_fps=timing_stats["throughput_fps"],
            retrieval_metrics=retrieval_res,
            text_retrieval_metrics=text_res,
            dataset_name=dataset_name,
            is_synthetic=dataset_is_synthetic,
        )

    def run_all(
        self,
        dataset: BenchmarkDataset,
        device: str = "cpu",
        candidate_ids: Optional[List[str]] = None,
    ) -> List[BenchmarkResult]:
        """Runs the benchmark across all registered or specified candidates."""
        all_adapters = self.registry.list_all()
        target_ids = candidate_ids or [a.metadata().candidate_id for a in all_adapters]

        results = []
        for cid in target_ids:
            res = self.evaluate_candidate(cid, dataset, device=device)
            results.append(res)
        return results

    @staticmethod
    def format_markdown_table(results: List[BenchmarkResult]) -> str:
        """Renders benchmark results into a clean markdown comparison table."""
        lines = [
            "| Candidate | Family | Dim | Latency (ms) | Top-1 Acc | MRR | Text Support | Status |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in results:
            if r.execution_status == "EXECUTED":
                lat = f"{r.inference_latency_ms:.1f}" if r.inference_latency_ms is not None else "N/A"
                top1 = f"{r.retrieval_metrics.get('top_1_accuracy', 0.0):.2f}" if r.retrieval_metrics else "N/A"
                mrr = f"{r.retrieval_metrics.get('mean_reciprocal_rank', 0.0):.2f}" if r.retrieval_metrics else "N/A"
                text_sup = "Yes" if r.supports_text else "No"
                status = "EXECUTED"
            else:
                lat = "N/A"
                top1 = "N/A"
                mrr = "N/A"
                text_sup = "Yes" if r.supports_text else "No"
                status = "NOT EXECUTED (un-staged)"

            lines.append(
                f"| **{r.candidate_name}** | {r.family} | {r.embedding_dimension} | {lat} | {top1} | {mrr} | {text_sup} | {status} |"
            )
        return "\n".join(lines)

    @staticmethod
    def export_json(results: List[BenchmarkResult], output_path: Union[Path, str]) -> None:
        """Serializes benchmark results to JSON file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = [r.model_dump(mode="json") for r in results]
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
