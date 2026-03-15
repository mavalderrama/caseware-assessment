from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Customer:
    id: int
    name: str
    email: str
    updated_at: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Case:
    id: int
    customer_id: int
    title: str
    description: str
    status: str
    updated_at: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TableManifest:
    row_count: int
    lake_paths: list[str]
    schema_fingerprint: str


@dataclass
class IngestManifest:
    run_id: str
    started_at: str
    finished_at: str
    dry_run: bool
    checkpoint_before: dict[str, str]
    checkpoint_after: dict[str, str]
    tables: dict[str, TableManifest]


@dataclass
class SearchResult:
    case_id: int
    score: float
    title: str
    status: str


@dataclass
class DeltaEvent:
    table: str
    run_id: str
    schema_fingerprint: str
    delta_row_count: int
    lake_paths: list[str]
    checkpoint_after: str
