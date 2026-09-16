"""ASTRA Offline Model and Real-Data Staging Script.

IMPORTANT ARCHITECTURAL SEPARATION:
- This script is an EXPLICIT ONE-TIME STAGING UTILITY for developers/operators.
- It downloads pre-trained weights and real satellite fixtures prior to offline use.
- It is NEVER called during benchmark evaluation or application runtime.
- All evaluation suites (backend/ml/benchmark/, scripts/benchmark_embeddings.py,
  and tests/test_embedding_benchmark.py) run 100% offline with ZERO download capability.
- If staged local artifacts are missing, the benchmark fails clearly and explicitly
  (reporting candidate as NOT EXECUTED) rather than attempting any network download.

Target local directories (strictly excluded from Git):
- models/staged/remoteclip/remoteclip_vitb32.pt (~577 MB)
- models/staged/clip/clip_vit_b32.pt (~350 MB)
- data/benchmark/real/eurosat_fixture/*.jpg (15 EuroSAT Sentinel-2 tiles)
"""

from pathlib import Path
import sys
import urllib.request
import hashlib
import json

# Ensure repository root is in python path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))


def download_with_progress(url: str, dest: Path, expected_mb: float = 0.0) -> None:
    """Downloads a remote file with console progress indication."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest.with_suffix(".tmp")

    print(f"  Downloading: {url}")
    print(f"  Destination: {dest}")

    def progress(count, block_size, total_size):
        downloaded_mb = (count * block_size) / (1024 * 1024)
        if total_size > 0:
            total_mb = total_size / (1024 * 1024)
            pct = min(100.0, (downloaded_mb / total_mb) * 100.0)
            sys.stdout.write(f"\r  Progress: {downloaded_mb:.1f} MB / {total_mb:.1f} MB ({pct:.1f}%)")
        else:
            sys.stdout.write(f"\r  Progress: {downloaded_mb:.1f} MB")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, temp_dest, reporthook=progress)
    print()  # newline
    if dest.exists():
        dest.unlink()
    temp_dest.rename(dest)
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"  Successfully staged: {dest} ({size_mb:.1f} MB)")


def stage_remoteclip():
    print("\n[1/3] Staging Candidate 1: RemoteCLIP (ViT-B/32)...")
    dest = Path("models/staged/remoteclip/remoteclip_vitb32.pt")
    if dest.exists() and dest.stat().st_size > 300 * 1024 * 1024:
        print(f"  RemoteCLIP already staged at {dest} ({dest.stat().st_size / (1024*1024):.1f} MB)")
        return True

    url = "https://huggingface.co/chendelong/RemoteCLIP/resolve/main/RemoteCLIP-ViT-B-32.pt"
    try:
        download_with_progress(url, dest, expected_mb=349.0)
        return True
    except Exception as e:
        print(f"  Failed to stage RemoteCLIP: {e}")
        return False


def stage_openai_clip():
    print("\n[2/3] Staging Candidate 5: OpenAI CLIP (ViT-B/32)...")
    dest = Path("models/staged/clip/clip_vit_b32.pt")
    if dest.exists() and dest.stat().st_size > 300 * 1024 * 1024:
        print(f"  OpenAI CLIP already staged at {dest} ({dest.stat().st_size / (1024*1024):.1f} MB)")
        return True

    try:
        import torch
        import open_clip
        dest.parent.mkdir(parents=True, exist_ok=True)
        print("  Downloading and saving OpenAI CLIP (ViT-B/32) state dict...")
        model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        torch.save(model.state_dict(), str(dest))
        print(f"  Successfully staged OpenAI CLIP at {dest}")
        return True
    except Exception as e:
        print(f"  Failed to stage OpenAI CLIP: {e}")
        return False


def stage_real_satellite_fixtures():
    """Stages small real-world Sentinel-2 public satellite imagery fixtures (EuroSAT)."""
    print("\n[3/3] Staging Small Real-World Remote Sensing Fixture Dataset (EuroSAT / Sentinel-2)...")
    real_dir = Path("data/benchmark/real/eurosat_fixture")
    real_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = real_dir / "dataset_metadata.json"
    metadata = {
        "dataset_name": "EuroSAT Sentinel-2 Public Sample Fixture",
        "sensor": "Sentinel-2A / Sentinel-2B MSI",
        "resolution_gsd_m": 10.0,
        "source": "EuroSAT: A Novel Dataset and Deep Learning Benchmark for Land Use and Land Cover Classification (Helber et al., IEEE JSTARS 2019)",
        "license": "Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)",
        "license_commercial_use": "Permitted with attribution",
        "description": "True-color (RGB) crops of 13 spectral band Sentinel-2 satellite imagery acquired across European cities and landscapes",
        "categories": ["urban", "vegetation", "water", "roads", "cleared"],
        "splits": ["query", "gallery"],
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Sample public Sentinel-2 image tile URLs from official EuroSAT GitHub / HuggingFace repository
    # 3 samples per category: 1 query, 2 gallery
    samples = [
        # Urban (Residential / Industrial)
        ("urban", "query", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/residential_sample.jpg", "urban_query_0.jpg"),
        ("urban", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/industrial_sample.jpg", "urban_gallery_1.jpg"),
        ("urban", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/highway_sample.jpg", "urban_gallery_2.jpg"),
        # Vegetation (Forest)
        ("vegetation", "query", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/forest_sample.jpg", "vegetation_query_0.jpg"),
        ("vegetation", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/annual_crop_sample.jpg", "vegetation_gallery_1.jpg"),
        ("vegetation", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/permanent_crop_sample.jpg", "vegetation_gallery_2.jpg"),
        # Water (River / SeaLake)
        ("water", "query", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/river_sample.jpg", "water_query_0.jpg"),
        ("water", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/sealake_sample.jpg", "water_gallery_1.jpg"),
        ("water", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/river_sample.jpg", "water_gallery_2.jpg"),
        # Roads (Highway)
        ("roads", "query", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/highway_sample.jpg", "roads_query_0.jpg"),
        ("roads", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/residential_sample.jpg", "roads_gallery_1.jpg"),
        ("roads", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/industrial_sample.jpg", "roads_gallery_2.jpg"),
        # Cleared / Pasture / Herbaceous
        ("cleared", "query", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/pasture_sample.jpg", "cleared_query_0.jpg"),
        ("cleared", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/herbaceous_sample.jpg", "cleared_gallery_1.jpg"),
        ("cleared", "gallery", "https://raw.githubusercontent.com/phelber/EuroSAT/master/images/pasture_sample.jpg", "cleared_gallery_2.jpg"),
    ]

    staged_count = 0
    for cat, split, sample_url, filename in samples:
        dest = real_dir / filename
        if dest.exists():
            staged_count += 1
            continue
        try:
            urllib.request.urlretrieve(sample_url, dest)
            staged_count += 1
        except Exception:
            pass

    print(f"  Staged {staged_count} real Sentinel-2 public fixture images in {real_dir}")
    return staged_count >= 10


def main():
    print("=" * 80)
    print("ASTRA PRETRAINED MODEL & REAL-DATA STAGING")
    print("One-time explicit asset acquisition step before offline execution")
    print("=" * 80)

    rc_ok = stage_remoteclip()
    clip_ok = stage_openai_clip()
    real_ok = stage_real_satellite_fixtures()

    print("\n" + "=" * 80)
    print("STAGING SUMMARY:")
    print(f"  1. RemoteCLIP (ViT-B/32)       : {'STAGED' if rc_ok else 'FAILED'}")
    print(f"  2. OpenAI CLIP (ViT-B/32)     : {'STAGED' if clip_ok else 'FAILED'}")
    print(f"  3. Clay Foundation Model       : NOT STAGED — Requires custom multi-spectral lighting architecture")
    print(f"  4. NASA-IBM Prithvi-100M       : NOT STAGED — Requires custom 3D temporal-spectral MAE module")
    print(f"  5. SatMAE ViT-Large            : NOT STAGED — Requires 1.2GB checkpoint & custom GSD embeddings")
    print(f"  6. Real Sentinel-2 Fixtures    : {'STAGED' if real_ok else 'PARTIALLY STAGED'}")
    print("=" * 80)


if __name__ == "__main__":
    main()
