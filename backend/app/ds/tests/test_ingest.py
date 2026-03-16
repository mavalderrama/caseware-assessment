"""
Ingest use-case tests.

All tests use SimpleTestCase (no database required).
Every port is replaced with a lightweight in-memory fake so the suite
runs without Postgres and without loading the SentenceTransformer model.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from app.ds.domain.entities import Case, Customer
from app.ds.use_cases.ingest import IngestUseCase

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

EPOCH = "1970-01-01T00:00:00+00:00"
TS1 = "2024-01-15T10:00:00+00:00"
TS2 = "2024-01-15T11:00:00+00:00"


def _make_customer(id: int, updated_at: str = TS1) -> Customer:
    raw = {
        "id": id,
        "name": f"Customer {id}",
        "email": f"c{id}@example.com",
        "updated_at": updated_at,
    }
    return Customer(
        id=id, name=f"Customer {id}", email=f"c{id}@example.com", updated_at=updated_at, raw=raw
    )


def _make_case(id: int, updated_at: str = TS1) -> Case:
    raw = {
        "id": id,
        "customer_id": 1,
        "title": f"Case {id}",
        "description": "",
        "status": "open",
        "updated_at": updated_at,
    }
    return Case(
        id=id,
        customer_id=1,
        title=f"Case {id}",
        description="",
        status="open",
        updated_at=updated_at,
        raw=raw,
    )


class FakeCustomerRepo:
    def __init__(self, rows: list[Customer] | None = None) -> None:
        self._rows = rows or []

    def fetch_since(self, since: str) -> list[Customer]:
        return self._rows

    def schema_fingerprint(self) -> str:
        return "aabbccdd00112233"


class FakeCaseRepo:
    def __init__(self, rows: list[Case] | None = None) -> None:
        self._rows = rows or []

    def fetch_since(self, since: str) -> list[Case]:
        return self._rows

    def schema_fingerprint(self) -> str:
        return "11223344aabbccdd"


class FakeCheckpointStore:
    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._data: dict[str, str] = initial or {"customers": EPOCH, "cases": EPOCH}
        self.saved: dict[str, str] | None = None
        self.save_called = 0

    def load(self) -> dict[str, str]:
        return dict(self._data)

    def save(self, checkpoint: dict[str, str]) -> None:
        self.saved = checkpoint
        self._data = dict(checkpoint)
        self.save_called += 1


class FakeLakeWriter:
    def __init__(self) -> None:
        self.writes: dict[str, list[dict]] = {}

    def write(self, table: str, rows: list[dict]) -> list[str]:
        self.writes[table] = list(rows)
        if not rows:
            return []
        return [f"lake/{table}/date=2024-01-15/data.jsonl"]


class FakeEventEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


class FakeSearchIndex:
    def __init__(self) -> None:
        self.rebuilt_from_lake = False
        self.rows: list[dict] = []

    def rebuild_from_lake(self, lake_dir: Path) -> None:
        self.rebuilt_from_lake = True

    def rebuild_from_lake_rows(self, rows: list[dict]) -> None:
        self.rows = list(rows)

    def search(self, query: str, top_k: int):
        return []


def _make_use_case(
    customers: list[Customer] | None = None,
    cases: list[Case] | None = None,
    checkpoint_store: FakeCheckpointStore | None = None,
    lake_writer: FakeLakeWriter | None = None,
    event_emitter: FakeEventEmitter | None = None,
    search_index: FakeSearchIndex | None = None,
    lake_dir: Path | None = None,
) -> tuple[IngestUseCase, FakeCheckpointStore, FakeLakeWriter, FakeEventEmitter, FakeSearchIndex]:
    cp = checkpoint_store or FakeCheckpointStore()
    lw = lake_writer or FakeLakeWriter()
    ee = event_emitter or FakeEventEmitter()
    si = search_index or FakeSearchIndex()
    ld = lake_dir or Path(tempfile.mkdtemp())
    uc = IngestUseCase(
        customer_repository=FakeCustomerRepo(customers),
        case_repository=FakeCaseRepo(cases),
        checkpoint_store=cp,
        lake_writer=lw,
        event_emitter=ee,
        search_index=si,
        lake_dir=ld,
    )
    return uc, cp, lw, ee, si


# ---------------------------------------------------------------------------
# Tests: checkpoint correctness
# ---------------------------------------------------------------------------


class TestCheckpointAdvancesOnSuccess(SimpleTestCase):
    def test_checkpoint_advances_after_successful_ingest(self):
        """Checkpoint must be saved with the max updated_at from the fetched rows."""
        customers = [_make_customer(1, TS1), _make_customer(2, TS2)]
        cases = [_make_case(10, TS1)]

        uc, cp, *_ = _make_use_case(customers=customers, cases=cases)
        manifest = uc.execute(dry_run=False)

        self.assertEqual(cp.save_called, 1)
        assert cp.saved is not None
        self.assertEqual(cp.saved["customers"], TS2)
        self.assertEqual(cp.saved["cases"], TS1)
        self.assertEqual(manifest.checkpoint_after["customers"], TS2)
        self.assertEqual(manifest.checkpoint_after["cases"], TS1)

    def test_checkpoint_not_advanced_on_dry_run(self):
        """Dry-run must not mutate the checkpoint."""
        uc, cp, lw, ee, _ = _make_use_case(
            customers=[_make_customer(1, TS1)],
            cases=[_make_case(10, TS1)],
        )
        manifest = uc.execute(dry_run=True)

        self.assertEqual(cp.save_called, 0)
        self.assertIsNone(cp.saved)
        self.assertTrue(manifest.dry_run)

    def test_dry_run_does_not_write_lake(self):
        """Lake writer must not be called during a dry run."""
        uc, _, lw, ee, _ = _make_use_case(
            customers=[_make_customer(1, TS1)],
            cases=[_make_case(10, TS1)],
        )
        uc.execute(dry_run=True)

        self.assertEqual(lw.writes, {})
        self.assertEqual(ee.events, [])

    def test_checkpoint_unchanged_when_no_new_rows(self):
        """If no new rows are fetched, checkpoint stays at its current value."""
        initial = {"customers": TS1, "cases": TS1}
        uc, cp, *_ = _make_use_case(
            customers=[],
            cases=[],
            checkpoint_store=FakeCheckpointStore(initial),
        )
        uc.execute(dry_run=False)

        self.assertEqual(cp.save_called, 1)
        assert cp.saved is not None
        self.assertEqual(cp.saved["customers"], TS1)
        self.assertEqual(cp.saved["cases"], TS1)


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------


class TestIdempotency(SimpleTestCase):
    def test_rerun_with_same_rows_overwrites_lake(self):
        """
        Running ingest twice with identical rows (same-day re-run) must overwrite,
        not append. The LakeWriter uses 'w' mode so the file is replaced.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            lake_dir = Path(tmpdir) / "lake"
            cp = FakeCheckpointStore()
            lw = FakeLakeWriter()

            cases = [_make_case(1, TS1), _make_case(2, TS2)]
            uc = IngestUseCase(
                customer_repository=FakeCustomerRepo(),
                case_repository=FakeCaseRepo(cases),
                checkpoint_store=cp,
                lake_writer=lw,
                event_emitter=FakeEventEmitter(),
                search_index=FakeSearchIndex(),
                lake_dir=lake_dir,
            )

            uc.execute(dry_run=False)
            first_write = list(lw.writes.get("cases", []))

            uc.execute(dry_run=False)
            second_write = list(lw.writes.get("cases", []))

            # Same rows written both times (overwrite, not duplicate)
            self.assertEqual(first_write, second_write)
            self.assertEqual(len(second_write), 2)

    def test_manifest_contains_expected_fields(self):
        """Returned manifest must include all required top-level fields."""
        uc, *_ = _make_use_case()
        manifest = uc.execute(dry_run=False)

        self.assertIsNotNone(manifest.run_id)
        self.assertIsNotNone(manifest.started_at)
        self.assertIsNotNone(manifest.finished_at)
        self.assertIn("customers", manifest.tables)
        self.assertIn("cases", manifest.tables)
        self.assertIn("customers", manifest.checkpoint_before)
        self.assertIn("cases", manifest.checkpoint_before)

    def test_search_index_rebuilt_after_ingest(self):
        """Search index rebuild_from_lake must be called on a successful ingest."""
        si = FakeSearchIndex()
        uc, *_ = _make_use_case(search_index=si)
        uc.execute(dry_run=False)

        self.assertTrue(si.rebuilt_from_lake)

    def test_search_index_not_rebuilt_on_dry_run(self):
        """Search index must NOT be rebuilt on dry_run=True."""
        si = FakeSearchIndex()
        uc, *_ = _make_use_case(search_index=si)
        uc.execute(dry_run=True)

        self.assertFalse(si.rebuilt_from_lake)
