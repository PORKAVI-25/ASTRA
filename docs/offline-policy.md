# A.S.T.R.A. Offline Operation Policy

**Status:** Mandatory Engineering Guardrail  
**Scope:** All runtime backend, frontend, and ML code in A.S.T.R.A.

---

## 1. Principle Statement

> **"ASTRA must operate completely offline after all approved models, libraries, and datasets have been staged. Runtime code must not depend on external APIs."**

Any code that requires an active Internet connection to execute searches, run change detection, render the user interface, or process satellite imagery fails project acceptance criteria.

---

## 2. Prohibited Runtime Practices

The following actions are strictly prohibited in runtime code:
1. **Dynamic Model Weight Downloads:** Invoking `torch.hub.load()`, `transformers.from_pretrained("<huggingface_repo>")`, or any library function that attempts to download model weights over HTTP at runtime.
2. **Cloud AI Inference Calls:** Calling OpenAI, Anthropic, Google Cloud Vertex AI, AWS Bedrock, or any external inference REST API.
3. **Live Remote Tile/Basemap Fetching:** Directly loading map tile servers (e.g., OpenStreetMap CDN, Google Maps API, Mapbox) without an offline cached tile provider or local GeoJSON fallback.
4. **External CDN Asset Dependencies:** Relying on CDN `<script>` or `<link>` tags in HTML (e.g., loading fonts, icons, or CSS frameworks from unpkg or cdnjs). All assets must be bundled locally.
5. **Runtime Telemetry / Phone-Home Beacons:** Embedding analytics trackers, Google Analytics, Sentry cloud beacons, or any reporting ping that reaches beyond localhost.

---

## 3. Approved Staging Protocol

To enable offline execution, assets must be staged during installation/preparation:

### 3.1 Python Dependencies
All packages must be installable via local wheels or pre-installed virtual environments:
```bash
pip install -r backend/requirements.txt
```

### 3.2 Machine Learning Model Weights
Weights must be stored in the designated staged cache directory:
```text
models/staged/
├── embeddings/
│   └── <model_name>/
│       ├── model.safetensors (or .pt)
│       └── config.json
└── change_detection/
    └── <model_name>/
        ├── weights.pt
        └── config.json
```
Model adapters must load strictly from local filesystem paths passed via `config.ASTRA_MODELS_CACHE_DIR`.

### 3.3 Geospatial Datasets & Benchmarks
Imagery scenes, tile manifests, and evaluation benchmarks must be placed in:
```text
data/
├── raw/            # Staged GeoTIFF/COG scenes
├── processed/      # Locally cut and normalized chips
├── manifests/      # Local JSON manifests
└── benchmark/      # Local ground-truth annotation pairs
```

---

## 4. Synthetic & Demo Data Governance

In accordance with **Critical Rule 9**:
- All mock, demo, or synthetically generated imagery tiles or manifests must have the flag `is_synthetic: true` explicitly embedded in their manifest.
- Benchmark evaluations must automatically filter out `is_synthetic: true` records to ensure absolute scientific validity.

---

## 5. Offline Compliance Verification

ASTRA includes an automated scanner to ensure no outbound network calls or external URLs are embedded in runtime code:
```powershell
python scripts/check_offline.py
```
This script scans all `.py`, `.ts`, and `.tsx` files in `backend/`, `frontend/src/`, `ml/`, and `geospatial/` for forbidden outbound URL patterns, cloud API SDKs, and dynamic weight download functions.
