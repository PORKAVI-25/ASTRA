"""Provenance recording and audit trail service."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.config import settings
from geospatial.contracts import ProvenanceRecord


class ProvenanceService:
    """Manages immutable lineage and processing records."""

    def __init__(self, provenance_dir: Optional[Path] = None):
        self.provenance_dir = provenance_dir or (settings.ASTRA_MANIFESTS_DIR / "provenance")
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

    def record_ingestion(
        self,
        source_scene_id: str,
        parameters: Dict[str, Any],
        executed_by: str = "astra.ingestion.service",
        processing_stage: str = "geospatial_ingestion_and_tiling",
    ) -> ProvenanceRecord:
        """Records an ingestion stage and persists the immutable provenance record."""
        now = datetime.now(timezone.utc)
        seed = f"{source_scene_id}:{processing_stage}:{now.isoformat()}"
        provenance_id = f"prov_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"

        record = ProvenanceRecord(
            provenance_id=provenance_id,
            source_scene_id=source_scene_id,
            target_tile_id=None,
            processing_stage=processing_stage,
            pipeline_version="0.1.0",
            parameters=parameters,
            executed_by=executed_by,
            timestamp=now,
        )

        record_file = self.provenance_dir / f"{provenance_id}.json"
        with open(record_file, "w", encoding="utf-8") as f:
            f.write(record.model_dump_json(indent=2))

        return record

    def get_provenance(self, provenance_id: str) -> Optional[ProvenanceRecord]:
        """Loads a provenance record by ID."""
        record_file = self.provenance_dir / f"{provenance_id}.json"
        if not record_file.exists():
            return None
        with open(record_file, "r", encoding="utf-8") as f:
            return ProvenanceRecord.model_validate_json(f.read())

    def list_provenance_for_scene(self, scene_id: str) -> List[ProvenanceRecord]:
        """Retrieves all provenance records for a given scene ID."""
        records = []
        for file in self.provenance_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    rec = ProvenanceRecord.model_validate_json(f.read())
                    if rec.source_scene_id == scene_id:
                        records.append(rec)
            except Exception:
                continue
        return sorted(records, key=lambda x: x.timestamp)


# Singleton
provenance_service = ProvenanceService()
