"""
Search use-case tests.

All tests use SimpleTestCase (no database required).
A hash-based FakeSearchIndex is used so there is no SentenceTransformer dependency.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.test import SimpleTestCase

from app.ds.domain.entities import SearchResult
from app.ds.use_cases.search import SearchUseCase

# ---------------------------------------------------------------------------
# Hash-based FakeSearchIndex (deterministic, no ML model required)
# ---------------------------------------------------------------------------


class FakeSearchIndex:
    """
    Deterministic similarity using XOR of MD5 hashes.

    Score = 1 / (1 + popcount(hash(query) XOR hash(text)))
    Tie-break: lower case_id first.
    """

    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = list(rows or [])

    def rebuild_from_lake(self, lake_dir: Path) -> None:
        pass

    def rebuild_from_lake_rows(self, rows: list[dict]) -> None:
        self._rows = list(rows)

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        query_hash = int(hashlib.md5(query.encode()).hexdigest(), 16)
        scored: list[tuple[int, float, str, str]] = []
        for row in self._rows:
            text = f"{row.get('title', '')} {row.get('status', '')}".strip()
            text_hash = int(hashlib.md5(text.encode()).hexdigest(), 16)
            bits_diff = bin(query_hash ^ text_hash).count("1")
            score = 1.0 / (1 + bits_diff)
            scored.append((row["id"], score, row.get("title", ""), row.get("status", "")))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return [
            SearchResult(case_id=s[0], score=s[1], title=s[2], status=s[3]) for s in scored[:top_k]
        ]


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

CASES = [
    {"id": 1, "title": "Login failure after password reset", "status": "open"},
    {"id": 2, "title": "Cannot export PDF report", "status": "closed"},
    {"id": 3, "title": "Dashboard slow to load", "status": "open"},
    {"id": 4, "title": "Email notifications not sent", "status": "pending"},
    {"id": 5, "title": "Password reset link expired", "status": "open"},
]


# ---------------------------------------------------------------------------
# Tests: search determinism
# ---------------------------------------------------------------------------


class TestSearchDeterminism(SimpleTestCase):
    def _make_use_case(self, rows=None) -> SearchUseCase:
        index = FakeSearchIndex(CASES if rows is None else rows)
        return SearchUseCase(search_index=index)

    def test_same_query_returns_same_order(self):
        """Given identical data, the same query must always return the same ordered results."""
        uc = self._make_use_case()
        results_a = uc.execute(query="login issue", top_k=5)
        results_b = uc.execute(query="login issue", top_k=5)

        self.assertEqual(len(results_a), len(results_b))
        for a, b in zip(results_a, results_b):
            self.assertEqual(a.case_id, b.case_id)
            self.assertAlmostEqual(a.score, b.score, places=9)

    def test_different_queries_may_return_different_orders(self):
        """Two semantically different queries should generally produce different rankings."""
        uc = self._make_use_case()
        r1 = uc.execute(query="login problem", top_k=5)
        r2 = uc.execute(query="email notification", top_k=5)

        ids1 = [r.case_id for r in r1]
        ids2 = [r.case_id for r in r2]
        # At least the top result should differ for these unrelated queries
        self.assertNotEqual(ids1, ids2)

    def test_top_k_limit_respected(self):
        """Result list must not exceed top_k."""
        uc = self._make_use_case()
        for k in (1, 2, 3):
            results = uc.execute(query="reset password", top_k=k)
            self.assertLessEqual(len(results), k)

    def test_top_k_larger_than_index_returns_all(self):
        """When top_k > index size, return all indexed items."""
        uc = self._make_use_case()
        results = uc.execute(query="anything", top_k=100)
        self.assertEqual(len(results), len(CASES))

    def test_empty_index_returns_empty_list(self):
        """Searching an empty index must return an empty list, not raise."""
        uc = self._make_use_case(rows=[])
        results = uc.execute(query="login", top_k=5)
        self.assertEqual(results, [])

    def test_results_contain_required_fields(self):
        """Each result must have case_id, score, title, status."""
        uc = self._make_use_case()
        results = uc.execute(query="password", top_k=3)
        for r in results:
            self.assertIsInstance(r.case_id, int)
            self.assertIsInstance(r.score, float)
            self.assertIsInstance(r.title, str)
            self.assertIsInstance(r.status, str)

    def test_results_sorted_by_score_descending(self):
        """Results must be ordered by descending score."""
        uc = self._make_use_case()
        results = uc.execute(query="password reset", top_k=5)
        scores = [r.score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_tie_break_by_case_id_ascending(self):
        """When two cases have the same score, the one with the lower case_id comes first."""
        # Create two cases that are identical (same text) so they score identically
        identical_cases = [
            {"id": 10, "title": "same title", "status": "open"},
            {"id": 20, "title": "same title", "status": "open"},
        ]
        uc = self._make_use_case(rows=identical_cases)
        results = uc.execute(query="same title", top_k=2)
        self.assertEqual(len(results), 2)
        self.assertAlmostEqual(results[0].score, results[1].score, places=9)
        self.assertLess(results[0].case_id, results[1].case_id)

    def test_rebuild_from_lake_rows_updates_index(self):
        """After rebuild_from_lake_rows, the index reflects new data."""
        index = FakeSearchIndex(rows=[])
        uc = SearchUseCase(search_index=index)

        results_before = uc.execute(query="anything", top_k=5)
        self.assertEqual(results_before, [])

        index.rebuild_from_lake_rows(CASES)
        results_after = uc.execute(query="login", top_k=5)
        self.assertGreater(len(results_after), 0)
