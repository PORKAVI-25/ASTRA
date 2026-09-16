"""Automated unit test suite for ASTRA Phase 2A Embedding Benchmark.

Covers candidate registration, adapter contracts, embedding shape and normalization,
deterministic dataset generation, metrics accuracy, unavailable model handling,
and strict offline execution enforcement.
"""

from pathlib import Path
import socket
import numpy as np
import pytest
import rasterio

from backend.ml.benchmark.candidates import (
    CandidateMetadata,
    CandidateRegistry,
    EmbeddingModelAdapter,
    ReferenceSpectralSpatialAdapter,
    RemoteCLIPAdapter,
    registry,
)
from backend.ml.benchmark.metrics import (
    compute_latency_statistics,
    compute_retrieval_metrics,
    cosine_similarity,
    normalize_vector,
    pairwise_cosine_similarity,
)
from backend.ml.benchmark.benchmark import (
    BenchmarkDataset,
    BenchmarkResult,
    EmbeddingBenchmarkRunner,
)


@pytest.fixture
def temp_benchmark_dir(tmp_path_factory) -> Path:
    """Fixture providing temporary isolated directory for synthetic benchmark data."""
    return tmp_path_factory.mktemp("astra_benchmarks")


@pytest.fixture
def sample_dataset(temp_benchmark_dir: Path) -> BenchmarkDataset:
    """Fixture generating a small deterministic 5-class synthetic dataset."""
    dataset = BenchmarkDataset(temp_benchmark_dir)
    dataset.generate(width=64, height=64)
    return dataset


def test_01_candidate_registration():
    """Verifies that all required candidate models are registered in CandidateRegistry."""
    expected_ids = {
        "remoteclip-vit-b-32",
        "clay-v0.1",
        "prithvi-100m",
        "satmae-vit-large",
        "openai-clip-vit-b-32",
        "reference-spectral-spatial",
    }
    registered_ids = {a.metadata().candidate_id for a in registry.list_all()}
    assert expected_ids.issubset(registered_ids)


def test_02_adapter_contract_and_metadata():
    """Verifies that all registered adapters conform strictly to the EmbeddingModelAdapter contract."""
    for adapter in registry.list_all():
        assert isinstance(adapter, EmbeddingModelAdapter)
        meta = adapter.metadata()
        assert isinstance(meta, CandidateMetadata)
        assert len(meta.candidate_id) > 0
        assert len(meta.display_name) > 0
        assert len(meta.family) > 0
        assert len(meta.architecture) > 0
        assert meta.embedding_dimension > 0
        assert len(meta.input_resolution) == 2
        assert meta.input_resolution[0] > 0 and meta.input_resolution[1] > 0
        assert len(meta.license) > 0

        # Availability check contract
        avail, reason = adapter.is_available()
        assert isinstance(avail, bool)
        assert isinstance(reason, str)
        assert len(reason) > 0


def test_03_reference_adapter_embedding_properties():
    """Verifies that reference adapter outputs 512-D unit-normalized float32 vectors deterministically."""
    adapter = ReferenceSpectralSpatialAdapter(seed=42)
    meta = adapter.metadata()
    assert meta.embedding_dimension == 512
    assert adapter.is_available()[0] is True

    # Deterministic test raster array (3 bands, 64x64)
    test_raster = np.arange(3 * 64 * 64, dtype=np.float32).reshape((3, 64, 64))

    emb1 = adapter.encode_image(test_raster)
    emb2 = adapter.encode_image(test_raster)

    assert isinstance(emb1, np.ndarray)
    assert emb1.shape == (512,)
    assert emb1.dtype == np.float32
    # Check L2 unit normalization
    norm = float(np.linalg.norm(emb1))
    assert pytest.approx(norm, abs=1e-4) == 1.0
    # Check strict determinism
    np.testing.assert_array_almost_equal(emb1, emb2)


def test_04_reference_adapter_batch_encoding():
    """Verifies batch image encoding produces row-normalized 2D arrays."""
    adapter = ReferenceSpectralSpatialAdapter(seed=42)
    rasters = [
        np.ones((3, 32, 32), dtype=np.float32) * 100,
        np.ones((3, 32, 32), dtype=np.float32) * 500,
        np.ones((3, 32, 32), dtype=np.float32) * 1000,
    ]
    batch_embs = adapter.encode_images(rasters)

    assert isinstance(batch_embs, np.ndarray)
    assert batch_embs.shape == (3, 512)
    for i in range(3):
        norm = float(np.linalg.norm(batch_embs[i]))
        assert pytest.approx(norm, abs=1e-4) == 1.0


def test_05_reference_adapter_text_encoding():
    """Verifies text encoding produces unit-normalized vectors and differentiates concepts."""
    adapter = ReferenceSpectralSpatialAdapter(seed=42)
    urban_emb = adapter.encode_text("urban built-up city area")
    water_emb = adapter.encode_text("deep water lake reservoir")

    assert urban_emb is not None
    assert water_emb is not None
    assert urban_emb.shape == (512,)
    assert water_emb.shape == (512,)
    assert pytest.approx(float(np.linalg.norm(urban_emb)), abs=1e-4) == 1.0
    assert pytest.approx(float(np.linalg.norm(water_emb)), abs=1e-4) == 1.0

    # Concepts must not be identical
    sim = cosine_similarity(urban_emb, water_emb)
    assert sim < 0.95


def test_06_deterministic_dataset_generation(sample_dataset: BenchmarkDataset):
    """Verifies deterministic synthetic dataset generation, categories, and georeferencing."""
    assert len(sample_dataset.CATEGORIES) == 5
    assert len(sample_dataset.query_items) == 5
    assert len(sample_dataset.gallery_items) == 10

    # Inspect one tile file
    first_query = sample_dataset.query_items[0]
    tile_path = Path(first_query.path)
    assert tile_path.exists()

    with rasterio.open(tile_path) as ds:
        assert ds.count == 3
        assert ds.width == 64
        assert ds.height == 64
        assert ds.crs is not None
        assert "32643" in ds.crs.to_string()
        tags = ds.tags()
        assert tags.get("IS_SYNTHETIC") == "true"
        assert tags.get("CATEGORY") == first_query.label


def test_07_retrieval_metrics_calculation():
    """Verifies cosine similarity, MRR, Top-1, and separation ratio on known vectors."""
    # Orthogonal basis: e0, e1, e2
    e0 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    e1 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    e2 = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    assert pytest.approx(cosine_similarity(e0, e0), abs=1e-6) == 1.0
    assert pytest.approx(cosine_similarity(e0, e1), abs=1e-6) == 0.0

    # Queries: class A (e0), class B (e1)
    queries = np.stack([e0, e1], axis=0)
    query_labels = ["class_A", "class_B"]

    # Gallery: class A (e0), class B (e1), class C (e2)
    gallery = np.stack([e0, e1, e2], axis=0)
    gallery_labels = ["class_A", "class_B", "class_C"]

    metrics = compute_retrieval_metrics(queries, query_labels, gallery, gallery_labels, top_k_ranks=(1, 2))
    assert metrics["top_1_accuracy"] == 1.0
    assert metrics["mean_reciprocal_rank"] == 1.0
    assert metrics["top_k_accuracy"][1] == 1.0
    assert metrics["top_k_accuracy"][2] == 1.0
    assert metrics["intra_class_similarity_mean"] > metrics["inter_class_similarity_mean"]


def test_08_unavailable_model_handling(sample_dataset: BenchmarkDataset):
    """Verifies that unavailable models report explicit status without fabricating numbers."""
    runner = EmbeddingBenchmarkRunner(registry=registry)
    result = runner.evaluate_candidate("clay-v0.1", sample_dataset)

    assert isinstance(result, BenchmarkResult)
    assert result.execution_status == "NOT EXECUTED — dependency/weights unavailable"
    assert result.failure_reason is not None
    assert len(result.failure_reason) > 0
    # Ensure zero fabricated numbers
    assert result.inference_latency_ms is None
    assert result.retrieval_metrics is None
    assert result.text_retrieval_metrics is None


def test_09_benchmark_suite_execution_and_schema(sample_dataset: BenchmarkDataset, tmp_path: Path):
    """Verifies end-to-end benchmark execution on reference adapter and JSON serialization."""
    runner = EmbeddingBenchmarkRunner(registry=registry)
    result = runner.evaluate_candidate("reference-spectral-spatial", sample_dataset)

    assert result.execution_status == "EXECUTED"
    assert result.inference_latency_ms is not None
    assert result.inference_latency_ms >= 0.0
    assert result.throughput_fps is not None
    assert result.retrieval_metrics is not None
    assert "top_1_accuracy" in result.retrieval_metrics
    assert "mean_reciprocal_rank" in result.retrieval_metrics
    assert result.text_retrieval_metrics is not None

    # Test export
    json_path = tmp_path / "results.json"
    runner.export_json([result], json_path)
    assert json_path.exists()
    assert len(json_path.read_text(encoding="utf-8")) > 100

    # Test markdown table formatting
    md = runner.format_markdown_table([result])
    assert "ASTRA Spectral-Spatial Reference Baseline" in md
    assert "EXECUTED" in md


def test_10_offline_mode_enforcement(sample_dataset: BenchmarkDataset, monkeypatch):
    """Verifies that the entire benchmark suite executes without attempting any network connection."""
    def guarded_connect(self, *args, **kwargs):
        raise RuntimeError("Prohibited outbound network connection attempted during benchmark!")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    runner = EmbeddingBenchmarkRunner(registry=registry)
    results = runner.run_all(sample_dataset, device="cpu")

    # Successfully ran without invoking socket.connect
    assert len(results) == len(registry.list_all())


def test_11_staged_models_local_paths_and_execution():
    """Verifies that staged foundation models (RemoteCLIP, OpenAI CLIP) execute from local paths."""
    for cid in ["remoteclip-vit-b-32", "openai-clip-vit-b-32"]:
        adapter = registry.get(cid)
        assert adapter is not None
        meta = adapter.metadata()
        assert meta.staged_weights_relative_path is not None
        weights_path = Path(meta.staged_weights_relative_path)
        assert weights_path.exists(), f"Staged weights missing for {cid}"

        avail, reason = adapter.is_available()
        assert avail is True
        assert "Ready" in reason

        # Test image encoding on 64x64 numpy array
        test_img = np.zeros((3, 64, 64), dtype=np.uint8)
        test_img[1, :, :] = 200  # green channel
        emb = adapter.encode_image(test_img)
        assert isinstance(emb, np.ndarray)
        assert emb.shape == (512,)
        assert emb.dtype == np.float32
        assert pytest.approx(float(np.linalg.norm(emb)), abs=1e-4) == 1.0


def test_12_real_dataset_fixture_loading():
    """Verifies that EuroSAT real Sentinel-2 satellite fixtures load properly with is_synthetic=False."""
    real_dir = Path("data/benchmark/real/eurosat_fixture")
    assert real_dir.exists()
    dataset = BenchmarkDataset(real_dir)
    loaded = dataset.load_real_fixture(real_dir)
    assert loaded is True
    assert len(dataset.query_items) == 5
    assert len(dataset.gallery_items) == 10
    for item in dataset.query_items + dataset.gallery_items:
        assert item.is_synthetic is False
        assert Path(item.path).exists()


def test_13_git_ignores_weight_binaries():
    """Verifies that model checkpoints and binary weights are excluded from Git tracking."""
    import subprocess
    check_paths = [
        "models/staged/remoteclip/remoteclip_vitb32.pt",
        "models/staged/clip/clip_vit_b32.pt",
        "data/benchmark/real/eurosat_fixture/urban_query_0.jpg",
    ]
    res = subprocess.run(
        ["git", "check-ignore"] + check_paths,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    ignored = [line.strip().replace("\\", "/") for line in res.stdout.splitlines() if line.strip()]
    for p in check_paths:
        assert p in ignored or any(p in ign for ign in ignored)
