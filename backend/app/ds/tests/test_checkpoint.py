"""
FileCheckpointStore infrastructure tests.

All tests use SimpleTestCase (no database required).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from app.ds.infrastructure.checkpoint import DEFAULT_CHECKPOINT, FileCheckpointStore

EPOCH = "1970-01-01T00:00:00+00:00"
TS1 = "2024-06-01T12:00:00+00:00"
TS2 = "2024-06-15T08:30:00+00:00"


class TestCheckpointLoadDefaults(SimpleTestCase):
    def test_load_returns_epoch_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp) / "state")
            cp = store.load()
            self.assertEqual(cp["customers"], EPOCH)
            self.assertEqual(cp["cases"], EPOCH)

    def test_load_default_matches_module_constant(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp) / "state")
            self.assertEqual(store.load(), DEFAULT_CHECKPOINT)

    def test_load_returns_independent_copy(self):
        """Mutating the returned dict must not affect subsequent loads."""
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp) / "state")
            cp = store.load()
            cp["customers"] = "tampered"
            self.assertEqual(store.load()["customers"], EPOCH)


class TestCheckpointSaveAndReload(SimpleTestCase):
    def test_save_then_load_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp) / "state")
            data = {"customers": TS1, "cases": TS2}
            store.save(data)
            self.assertEqual(store.load(), data)

    def test_save_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "nested" / "state"
            store = FileCheckpointStore(state_dir)
            store.save({"customers": TS1, "cases": TS1})
            self.assertTrue((state_dir / "checkpoint.json").exists())

    def test_save_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            store = FileCheckpointStore(state_dir)
            store.save({"customers": TS1, "cases": TS2})
            raw = json.loads((state_dir / "checkpoint.json").read_text())
            self.assertEqual(raw["customers"], TS1)
            self.assertEqual(raw["cases"], TS2)

    def test_successive_saves_last_write_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FileCheckpointStore(Path(tmp) / "state")
            store.save({"customers": TS1, "cases": TS1})
            store.save({"customers": TS2, "cases": TS2})
            cp = store.load()
            self.assertEqual(cp["customers"], TS2)
            self.assertEqual(cp["cases"], TS2)

    def test_no_tmp_file_left_after_successful_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            store = FileCheckpointStore(state_dir)
            store.save({"customers": TS1, "cases": TS1})
            tmp_files = list(state_dir.glob("*.tmp"))
            self.assertEqual(tmp_files, [])
