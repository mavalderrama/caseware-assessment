from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .entities import Case, Customer, SearchResult


class CustomerRepositoryPort(Protocol):
    def fetch_since(self, since: str) -> list[Customer]: ...

    def schema_fingerprint(self) -> str: ...


class CaseRepositoryPort(Protocol):
    def fetch_since(self, since: str) -> list[Case]: ...

    def schema_fingerprint(self) -> str: ...


class CheckpointStorePort(Protocol):
    def load(self) -> dict[str, str]: ...

    def save(self, checkpoint: dict[str, str]) -> None: ...


class LakeWriterPort(Protocol):
    def write(self, table: str, rows: list[dict]) -> list[str]: ...


class EventEmitterPort(Protocol):
    def emit(self, event: dict) -> None: ...


class SearchIndexPort(Protocol):
    def rebuild_from_lake(self, lake_dir: Path) -> None: ...

    def rebuild_from_lake_rows(self, rows: list[dict]) -> None: ...

    def search(self, query: str, top_k: int) -> list[SearchResult]: ...
