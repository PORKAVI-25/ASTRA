# ASTRA Embedding Model Benchmark Results Summary

> [!NOTE]
> **Prototype Model-Selection Disclaimer**: This benchmark is a controlled local evaluation gate designed specifically for comparative model selection and offline feasibility verification across candidate architectures. The reported metrics reflect performance on small, deterministic benchmark fixtures (15 real Sentinel-2 EuroSAT chips and 15 synthetic UTM chips across 5 land-cover categories). They do **NOT** represent universal operational accuracy across all Earth Observation satellites, sensors, or global geographies.

---

## 1. Real Sentinel-2 Satellite Dataset Evaluation (EuroSAT Fixture)

- **Dataset**: EuroSAT Sentinel-2 MSI Public Sample (Helber et al., IEEE JSTARS 2019)
- **Fixture Size**: 15 real satellite image tiles ($64 \times 64$ px, 10m GSD, 3-band optical RGB)
- **Categories**: `urban` (Residential/Industrial), `vegetation` (Forest), `water` (River), `roads` (Highway), `cleared` (Pasture)
- **Split**: 5 Query Tiles (1 per class), 10 Gallery Tiles (2 per class)
- **Artifact Status**: Real imagery chips (`*.jpg`) are **local staged artifacts** (intentionally NOT committed to Git). Provenance metadata (`dataset_metadata.json`) is tracked.
- **Environment**: Local Windows 11 CPU (`.venv`, Python 3.14.3, PyTorch CPU)
- **Network**: Zero outbound network requests (100% offline local execution)

### A. Executed Models (Measured Results)
| Candidate Name | Architecture | Dim | Latency (CPU) | Top-1 Acc | MRR | Separation Ratio | Status |
|---|---|---|---|---|---|---|---|
| **RemoteCLIP (ViT-B/32)** | ViT-B/32 | 512 | **82.1 ms** | **0.60** | **0.72** | **1.1082** | **EXECUTED** |
| **OpenAI CLIP Baseline** | ViT-B/32 | 512 | **71.0 ms** | **0.40** | **0.63** | **1.0397** | **EXECUTED** |
| **ASTRA Reference Baseline** | Spectral-Spatial | 512 | **1.5 ms** | **0.40** | **0.52** | **1.0016** | **EXECUTED** |

### B. Unexecuted Candidate Models (Documented Limitations)
| Candidate Name | Architecture | Dim | Status | Exact Documented Reason |
|---|---|---|---|---|
| **Clay Foundation Model (v0.1)** | ViT-B (MAE) | 768 | **NOT EXECUTED** | Requires custom PyTorch Lightning module (`ClayMAEModule`) and multi-band (10-channel) sensor cubes |
| **NASA-IBM Prithvi-100M** | 3D-MAE ViT | 768 | **NOT EXECUTED** | Requires custom 3D temporal-spectral MAE module (`Prithvi.py`) and multi-temporal HLS cubes |
| **SatMAE (ViT-Large)** | ViT-L/16 | 1024 | **NOT EXECUTED** | Requires 1.2 GB checkpoint staging and custom Ground Sample Distance (GSD) scale-positional encoding classes |

---

## 2. Synthetic Dataset Evaluation (ASTRA Deterministic Fixture)

- **Dataset**: ASTRA Deterministic Synthetic GeoTIFFs (EPSG:32643, UTM Zone 43N)
- **Fixture Size**: 15 georeferenced GeoTIFF chips ($128 \times 128$ px, 3 bands)
- **Flag**: `is_synthetic: true` (strictly separated from operational data per Rule 9)
- **Categories**: `urban`, `vegetation`, `water`, `roads`, `cleared`
- **Split**: 5 Query Tiles, 10 Gallery Tiles

### A. Executed Models (Measured Results)
| Candidate Name | Architecture | Dim | Latency (CPU) | Top-1 Acc | MRR | Separation Ratio | Status |
|---|---|---|---|---|---|---|---|
| **RemoteCLIP (ViT-B/32)** | ViT-B/32 | 512 | **72.8 ms** | **1.00** | **1.00** | **1.4482** | **EXECUTED** |
| **OpenAI CLIP Baseline** | ViT-B/32 | 512 | **78.0 ms** | **1.00** | **1.00** | **1.1699** | **EXECUTED** |
| **ASTRA Reference Baseline** | Spectral-Spatial | 512 | **5.4 ms** | **1.00** | **1.00** | **1.3506** | **EXECUTED** |

---

## 3. Key Observations & Findings

1. **Domain Adaptation Impact on Real Satellite Imagery**:
   - RemoteCLIP outperforms generic OpenAI CLIP by **+20% on Top-1 retrieval accuracy** (0.60 vs. 0.40) on real Sentinel-2 satellite imagery.
   - RemoteCLIP maintains a clear inter- vs intra-class separation ratio (**1.1082** vs. **1.0397** for generic CLIP), demonstrating superior discrimination between overhead landscape features.
2. **CPU Feasibility**:
   - Both ViT-B/32 models run efficiently on CPU at **70–82 ms per tile** (~12–14 tiles/sec), validating local offline execution without GPU requirements.
3. **Reproducibility & Air-Gap Compliance**:
   - Both model checkpoints are staged locally under `models/staged/` and ignored by Git.
   - Zero remote network connections are made during benchmark execution.