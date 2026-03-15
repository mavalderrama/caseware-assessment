from __future__ import annotations

from ..domain.entities import SearchResult
from ..domain.ports import SearchIndexPort


class SearchUseCase:
    def __init__(self, search_index: SearchIndexPort) -> None:
        self._index = search_index

    def execute(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return self._index.search(query, top_k)
