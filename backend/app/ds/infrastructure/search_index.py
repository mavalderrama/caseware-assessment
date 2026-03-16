from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..domain.entities import SearchResult


class PgvectorSearchIndex:
    """
    Search index backed by pgvector in Postgres.

    Embeddings are stored in Case.embedding (VectorField(384)).
    Model loading uses a class-level double-checked lock to load once per process.
    """

    _model: Any = None
    _model_lock: threading.Lock = threading.Lock()

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    @classmethod
    def _get_model(cls, model_name: str) -> Any:
        if cls._model is None:
            with cls._model_lock:
                if cls._model is None:
                    from sentence_transformers import SentenceTransformer

                    cls._model = SentenceTransformer(model_name)
        return cls._model

    def rebuild_from_lake(self, lake_dir: Path) -> None:
        """Read all case JSONL partitions; deduplicate by id (latest partition wins)."""
        cases_dir = Path(lake_dir) / "cases"
        if not cases_dir.exists():
            return
        rows_by_id: dict[int, dict] = {}
        for jsonl_file in sorted(cases_dir.rglob("data.jsonl")):
            with open(jsonl_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    rows_by_id[row["id"]] = row
        self.rebuild_from_lake_rows(list(rows_by_id.values()))

    def rebuild_from_lake_rows(self, rows: list[dict]) -> None:
        """Encode rows and bulk-update Case.embedding in Postgres."""
        if not rows:
            return

        from ..infrastructure.models import Case as CaseModel

        model = self._get_model(self._model_name)
        texts = [
            f"{r.get('title', '')} {r.get('description', '')} {r.get('status', '')}".strip()
            for r in rows
        ]
        embeddings = model.encode(texts, normalize_embeddings=True)
        cases = [CaseModel(id=r["id"]) for r in rows]
        for case, emb in zip(cases, embeddings):
            case.embedding = emb.tolist()
        CaseModel.objects.bulk_update(cases, ["embedding"])  # type: ignore[attr-defined]

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        """Cosine similarity via pgvector. Tie-break by id for determinism."""
        from pgvector.django import CosineDistance

        from ..infrastructure.models import Case as CaseModel

        model = self._get_model(self._model_name)
        query_vec = model.encode([query], normalize_embeddings=True)[0]

        qs = (
            CaseModel.objects.filter(embedding__isnull=False)  # type: ignore[attr-defined]
            .annotate(distance=CosineDistance("embedding", query_vec.tolist()))
            .order_by("distance", "id")[:top_k]
        )
        return [
            SearchResult(
                case_id=c.id,
                score=float(1.0 - c.distance),
                title=c.title,
                status=c.status,
            )
            for c in qs
        ]
