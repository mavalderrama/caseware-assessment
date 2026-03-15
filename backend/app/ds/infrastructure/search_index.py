from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..domain.entities import SearchResult


class InMemorySearchIndex:
    """
    In-memory search index backed by SentenceTransformer embeddings.

    Thread-safe: index rebuilds and searches share an RLock.
    Model loading uses a class-level double-checked lock to load once per process.
    """

    _model: Any = None
    _model_lock: threading.Lock = threading.Lock()

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        # entries: list of (case_id, title, status, embedding_ndarray)
        self._entries: list[tuple[int, str, str, Any]] = []
        self._lock = threading.RLock()

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
        """Encode rows and replace the entire index atomically."""
        if not rows:
            with self._lock:
                self._entries = []
            return

        model = self._get_model(self._model_name)
        texts = [
            f"{r.get('title', '')} {r.get('description', '')} {r.get('status', '')}".strip()
            for r in rows
        ]
        embeddings = model.encode(texts, normalize_embeddings=True)
        entries = [
            (r["id"], r.get("title", ""), r.get("status", ""), emb)
            for r, emb in zip(rows, embeddings)
        ]
        with self._lock:
            self._entries = entries

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        """Cosine similarity via dot product on L2-normalised vectors. Stable sort: (-score, case_id)."""
        import numpy as np

        model = self._get_model(self._model_name)
        query_vec = model.encode([query], normalize_embeddings=True)[0]

        with self._lock:
            entries = list(self._entries)

        if not entries:
            return []

        matrix = np.stack([e[3] for e in entries])
        scores = matrix @ query_vec  # shape (n,)

        scored = [
            (entries[i][0], float(scores[i]), entries[i][1], entries[i][2])
            for i in range(len(entries))
        ]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return [
            SearchResult(case_id=s[0], score=s[1], title=s[2], status=s[3]) for s in scored[:top_k]
        ]
