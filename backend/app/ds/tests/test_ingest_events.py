"""
Ingest use-case — delta events and manifest completeness tests.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from django.test import SimpleTestCase

from app.ds.domain.entities import Case, Customer
from app.ds.use_cases.ingest import IngestUseCase

EPOCH = "1970-01-01T00:00:00+00:00"
TS1 = "2024-03-01T09:00:00+00:00"
TS2 = "2024-03-01T10:00:00+00:00"


# ---------------------------------------------------------------------------
# Fakes (minimal — only what each test needs)
# ---------------------------------------------------------------------------


class FakeRepo:
    def __init__(self, rows: list, fp: str = "deadbeef12345678") -> None:
        self._rows = rows
        self._fp = fp

    def fetch_since(self, since: str) -> list:
        return self._rows

    def schema_fingerprint(self) -> str:
        return self._fp


class FakeCheckpointStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {"customers": EPOCH, "cases": EPOCH}
        self.saved: dict[str, str] | None = None

    def load(self) -> dict[str, str]:
        return dict(self._data)

    def save(self, cp: dict[str, str]) -> None:
        self.saved = cp
        self._data = dict(cp)


class FakeLakeWriter:
    def write(self, table: str, rows: list[dict]) -> list[str]:
        return [f"lake/{table}/date=2024-03-01/data.jsonl"] if rows else []


class FakeEventEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


class FakeSearchIndex:
    def rebuild_from_lake(self, lake_dir: Path) -> None:
        pass

    def rebuild_from_lake_rows(self, rows: list[dict]) -> None:
        pass

    def search(self, query: str, top_k: int) -> list:
        return []


def _customer(i: int, ts: str = TS1) -> Customer:
    raw = {"id": i, "name": f"C{i}", "email": f"c{i}@x.com", "updated_at": ts}
    return Customer(id=i, name=raw["name"], email=raw["email"], updated_at=ts, raw=raw)


def _case(i: int, ts: str = TS1) -> Case:
    raw = {"id": i, "customer_id": 1, "title": f"Case {i}", "description": "", "status": "open", "updated_at": ts}
    return Case(id=i, customer_id=1, title=raw["title"], description="", status="open", updated_at=ts, raw=raw)


def _make_uc(customers=None, cases=None, emitter=None):
    ee = emitter or FakeEventEmitter()
    uc = IngestUseCase(
        customer_repository=FakeRepo(customers or []),
        case_repository=FakeRepo(cases or []),
        checkpoint_store=FakeCheckpointStore(),
        lake_writer=FakeLakeWriter(),
        event_emitter=ee,
        search_index=FakeSearchIndex(),
        lake_dir=Path(tempfile.mkdtemp()),
    )
    return uc, ee


# ---------------------------------------------------------------------------
# Tests: delta events
# ---------------------------------------------------------------------------


class TestDeltaEvents(SimpleTestCase):
    def test_two_events_emitted_one_per_table(self):
        uc, ee = _make_uc(customers=[_customer(1)], cases=[_case(10)])
        uc.execute(dry_run=False)
        self.assertEqual(len(ee.events), 2)

    def test_event_tables_are_customers_and_cases(self):
        uc, ee = _make_uc(customers=[_customer(1)], cases=[_case(10)])
        uc.execute(dry_run=False)
        tables = {e["table"] for e in ee.events}
        self.assertEqual(tables, {"customers", "cases"})

    def test_event_contains_required_fields(self):
        uc, ee = _make_uc(customers=[_customer(1)], cases=[_case(10)])
        uc.execute(dry_run=False)
        for event in ee.events:
            for field in ("table", "run_id", "schema_fingerprint", "delta_row_count", "lake_paths", "checkpoint_after"):
                self.assertIn(field, event, f"Missing field '{field}' in event")

    def test_event_run_id_matches_manifest(self):
        uc, ee = _make_uc(customers=[_customer(1)], cases=[_case(10)])
        manifest = uc.execute(dry_run=False)
        for event in ee.events:
            self.assertEqual(event["run_id"], manifest.run_id)

    def test_event_delta_row_count_correct(self):
        uc, ee = _make_uc(customers=[_customer(1), _customer(2)], cases=[_case(10)])
        uc.execute(dry_run=False)
        by_table = {e["table"]: e for e in ee.events}
        self.assertEqual(by_table["customers"]["delta_row_count"], 2)
        self.assertEqual(by_table["cases"]["delta_row_count"], 1)

    def test_event_schema_fingerprint_matches_repo(self):
        customer_fp = "aaaa000011110000"
        case_fp = "bbbb111100001111"
        uc = IngestUseCase(
            customer_repository=FakeRepo([_customer(1)], fp=customer_fp),
            case_repository=FakeRepo([_case(1)], fp=case_fp),
            checkpoint_store=FakeCheckpointStore(),
            lake_writer=FakeLakeWriter(),
            event_emitter=(ee := FakeEventEmitter()),
            search_index=FakeSearchIndex(),
            lake_dir=Path(tempfile.mkdtemp()),
        )
        uc.execute(dry_run=False)
        by_table = {e["table"]: e for e in ee.events}
        self.assertEqual(by_table["customers"]["schema_fingerprint"], customer_fp)
        self.assertEqual(by_table["cases"]["schema_fingerprint"], case_fp)

    def test_no_events_emitted_on_dry_run(self):
        uc, ee = _make_uc(customers=[_customer(1)], cases=[_case(10)])
        uc.execute(dry_run=True)
        self.assertEqual(ee.events, [])

    def test_events_emitted_even_with_zero_rows(self):
        """An event per table is still emitted when delta is 0 (confirms pipeline ran)."""
        uc, ee = _make_uc(customers=[], cases=[])
        uc.execute(dry_run=False)
        self.assertEqual(len(ee.events), 2)

    def test_event_lake_paths_empty_when_no_rows(self):
        uc, ee = _make_uc(customers=[], cases=[])
        uc.execute(dry_run=False)
        for event in ee.events:
            self.assertEqual(event["lake_paths"], [])


# ---------------------------------------------------------------------------
# Tests: manifest completeness
# ---------------------------------------------------------------------------


class TestManifestCompleteness(SimpleTestCase):
    def test_run_id_is_valid_uuid(self):
        uc, _ = _make_uc()
        manifest = uc.execute(dry_run=False)
        uuid.UUID(manifest.run_id)  # raises if invalid

    def test_started_at_before_finished_at(self):
        uc, _ = _make_uc()
        manifest = uc.execute(dry_run=False)
        self.assertLessEqual(manifest.started_at, manifest.finished_at)

    def test_manifest_dry_run_flag_propagated(self):
        uc, _ = _make_uc()
        self.assertTrue(uc.execute(dry_run=True).dry_run)
        self.assertFalse(uc.execute(dry_run=False).dry_run)

    def test_table_manifest_schema_fingerprint_present(self):
        uc, _ = _make_uc(cases=[_case(1)])
        manifest = uc.execute(dry_run=False)
        self.assertTrue(manifest.tables["cases"].schema_fingerprint)
        self.assertTrue(manifest.tables["customers"].schema_fingerprint)

    def test_table_manifest_row_count_matches_fetched(self):
        uc, _ = _make_uc(customers=[_customer(1), _customer(2)], cases=[_case(10)])
        manifest = uc.execute(dry_run=False)
        self.assertEqual(manifest.tables["customers"].row_count, 2)
        self.assertEqual(manifest.tables["cases"].row_count, 1)

    def test_lake_paths_populated_when_rows_present(self):
        uc, _ = _make_uc(cases=[_case(1)])
        manifest = uc.execute(dry_run=False)
        self.assertGreater(len(manifest.tables["cases"].lake_paths), 0)

    def test_lake_paths_empty_when_no_rows(self):
        uc, _ = _make_uc(cases=[])
        manifest = uc.execute(dry_run=False)
        self.assertEqual(manifest.tables["cases"].lake_paths, [])

    def test_checkpoint_before_and_after_in_manifest(self):
        uc, _ = _make_uc(customers=[_customer(1, TS2)], cases=[_case(1, TS1)])
        manifest = uc.execute(dry_run=False)
        self.assertEqual(manifest.checkpoint_before["customers"], EPOCH)
        self.assertEqual(manifest.checkpoint_after["customers"], TS2)
