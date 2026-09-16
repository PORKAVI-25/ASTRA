"""ASTRA Satellite Embedding Model Benchmark CLI Runner.

Executes the model selection benchmark across candidate architectures using
both deterministic synthetic evaluation rasters and real-world satellite imagery fixtures,
enforcing strict offline operation.
"""

import argparse
from pathlib import Path
import platform
import sys
from typing import List, Optional

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure repository root is in python path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.ml.benchmark.benchmark import BenchmarkDataset, BenchmarkResult, EmbeddingBenchmarkRunner
from backend.ml.benchmark.candidates import registry


def print_banner():
    print("=" * 90)
    print("ASTRA PHASE 2A.1: REAL MODEL STAGING AND SATELLITE EMBEDDING BENCHMARK")
    print("Multi-Model Evaluation Across Synthetic Rasters and Real Sentinel-2 Satellite Imagery")
    print("=" * 90)
    print(f"Platform: {platform.system()} {platform.release()} | Python: {platform.python_version()}")
    print("Offline Policy: Strict Air-Gap (Zero Remote Network Calls)")
    print("-" * 90)


def display_results_table(title: str, results: List[BenchmarkResult]):
    print(f"\n{title}")
    print("-" * 90)
    print(f"{'Candidate Name':<34} {'Family':<22} {'Dim':<5} {'Latency':<10} {'Top-1':<7} {'MRR':<6} {'Status'}")
    print("-" * 90)

    for r in results:
        if r.execution_status == "EXECUTED":
            lat_str = f"{r.inference_latency_ms:.1f} ms" if r.inference_latency_ms else "N/A"
            top1_str = f"{r.retrieval_metrics.get('top_1_accuracy', 0.0):.2f}" if r.retrieval_metrics else "N/A"
            mrr_str = f"{r.retrieval_metrics.get('mean_reciprocal_rank', 0.0):.2f}" if r.retrieval_metrics else "N/A"
            status_str = "EXECUTED"
        else:
            lat_str = "N/A"
            top1_str = "N/A"
            mrr_str = "N/A"
            status_str = "NOT EXECUTED"

        print(f"{r.candidate_name:<34} {r.family[:21]:<22} {r.embedding_dimension:<5} {lat_str:<10} {top1_str:<7} {mrr_str:<6} {status_str}")
    print("-" * 90)


def display_metrics_breakdown(results: List[BenchmarkResult]):
    print("\n[Detailed Metrics & Statistical Breakdown]:")
    for r in results:
        if r.execution_status == "EXECUTED":
            print(f"\n  ✓ {r.candidate_name} ({r.dataset_name}):")
            print(f"      Architecture    : {r.architecture}")
            print(f"      Embedding Dim   : {r.embedding_dimension}")
            print(f"      Model Size      : {r.model_size_mb} MB ({r.parameter_count_m}M params)")
            print(f"      Mean Latency    : {r.inference_latency_ms:.2f} ms (p95: {r.p95_latency_ms:.2f} ms)")
            print(f"      Throughput      : {r.throughput_fps:.1f} tiles/sec on CPU")
            if r.retrieval_metrics:
                print(f"      Image Top-1 Acc : {r.retrieval_metrics['top_1_accuracy']}")
                print(f"      Image MRR       : {r.retrieval_metrics['mean_reciprocal_rank']}")
                print(f"      Intra-class Sim : {r.retrieval_metrics['intra_class_similarity_mean']}")
                print(f"      Inter-class Sim : {r.retrieval_metrics['inter_class_similarity_mean']}")
                print(f"      Separation Ratio: {r.retrieval_metrics['separation_ratio']}")
            if r.text_retrieval_metrics:
                print(f"      Text Top-1 Acc  : {r.text_retrieval_metrics['top_1_accuracy']}")
                print(f"      Text MRR        : {r.text_retrieval_metrics['mean_reciprocal_rank']}")
        else:
            print(f"\n  - {r.candidate_name}:")
            print(f"      Status          : {r.execution_status}")
            print(f"      Reason          : {r.failure_reason}")
            print(f"      Offline Staging : {r.offline_compatibility_status}")


def main():
    parser = argparse.ArgumentParser(description="Run ASTRA Satellite Embedding Model Benchmark")
    parser.add_argument(
        "--dataset",
        choices=["synthetic", "real", "both"],
        default="both",
        help="Evaluation dataset: synthetic, real, or both (default: both)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/benchmark/synthetic",
        help="Directory to store deterministic synthetic benchmark rasters",
    )
    parser.add_argument(
        "--real-dir",
        type=str,
        default="data/benchmark/real/eurosat_fixture",
        help="Directory containing real Sentinel-2 fixture imagery",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="data/benchmark/embedding_benchmark_results.json",
        help="Destination path for benchmark results JSON",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/benchmark-table.md",
        help="Destination path for markdown benchmark table",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Inference compute device (cpu or cuda)",
    )
    parser.add_argument(
        "--candidate",
        type=str,
        default=None,
        help="Specific candidate ID to evaluate (default: all registered candidates)",
    )
    args = parser.parse_args()

    print_banner()

    runner = EmbeddingBenchmarkRunner(registry=registry)
    target_candidates = [args.candidate] if args.candidate else None
    all_results: List[BenchmarkResult] = []

    # 1. Synthetic Dataset Benchmark
    if args.dataset in ["synthetic", "both"]:
        synth_dir = Path(args.data_dir)
        print(f"\n[1/3] Preparing deterministic synthetic dataset at: {synth_dir}")
        synth_dataset = BenchmarkDataset(synth_dir)
        synth_dataset.generate(width=128, height=128)
        print(f"      Generated {len(synth_dataset.query_items)} query tiles and {len(synth_dataset.gallery_items)} gallery tiles")
        print(f"      Categories: {', '.join(BenchmarkDataset.CATEGORIES)}")

        print(f"\n      Running benchmark on SYNTHETIC dataset (device: {args.device.upper()})...")
        synth_results = runner.run_all(dataset=synth_dataset, device=args.device, candidate_ids=target_candidates)
        all_results.extend(synth_results)
        display_results_table("SYNTHETIC DATASET BENCHMARK RESULTS", synth_results)

    # 2. Real Sentinel-2 Dataset Benchmark
    if args.dataset in ["real", "both"]:
        real_dir = Path(args.real_dir)
        print(f"\n[2/3] Checking real-world satellite imagery fixture at: {real_dir}")
        real_dataset = BenchmarkDataset(real_dir)
        loaded = real_dataset.load_real_fixture(real_dir)

        if loaded:
            print(f"      Loaded {len(real_dataset.query_items)} query tiles and {len(real_dataset.gallery_items)} gallery tiles")
            print(f"      Source: EuroSAT Sentinel-2 MSI (10m GSD, Public CC BY-SA 4.0)")
            print(f"\n      Running benchmark on REAL Sentinel-2 dataset (device: {args.device.upper()})...")
            real_results = runner.run_all(dataset=real_dataset, device=args.device, candidate_ids=target_candidates)
            all_results.extend(real_results)
            display_results_table("REAL SENTINEL-2 DATASET BENCHMARK RESULTS (EuroSAT)", real_results)
        else:
            print(f"      REAL-DATA BENCHMARK: NOT EXECUTED — Fixture files not found at {real_dir}")

    # 3. Metrics breakdown
    print("\n[3/3] Comprehensive Candidate Breakdown:")
    display_metrics_breakdown(all_results)

    # 4. Export artifacts
    if args.output_json:
        runner.export_json(all_results, args.output_json)
        print(f"\n  Saved benchmark JSON to: {args.output_json}")

    if args.output_md:
        md_content = runner.format_markdown_table(all_results)
        Path(args.output_md).write_text(md_content, encoding="utf-8")
        print(f"  Saved benchmark Markdown table to: {args.output_md}")

    print("\n[COMPLETE]: Phase 2A.1 Model Staging & Benchmark evaluation complete.")


if __name__ == "__main__":
    main()
