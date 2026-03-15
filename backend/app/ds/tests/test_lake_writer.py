"""
LakeWriter infrastructure tests.

All tests use SimpleTestCase (no database required).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from app.ds.infrastructure.lake_writer import LakeWriter


class TestLakeWriterEmptyRows(SimpleTestCase):
    def test_empty_rows_returns_no_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            lw = LakeWriter(Path(tmp) / "lake")
            paths = lw.write("cases", [])
            self.assertEqual(paths, [])

    def test_empty_rows_creates_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            lake_dir = Path(tmp) / "lake"
            lw = LakeWriter(lake_dir)
            lw.write("cases", [])
            self.assertFalse((lake_dir / "cases").exists())


class TestLakeWriterOutput(SimpleTestCase):
    _ROWS = [
        {"id": 1, "title": "Alpha", "status": "open"},
        {"id": 2, "title": "Beta",  "status": "closed"},
    ]

    def _write(self, table: str = "cases") -> tuple[LakeWriter, Path, list[str]]:
        self._tmp = tempfile.TemporaryDirectory()
        lake_dir = Path(self._tmp.name) / "lake"
        lw = LakeWriter(lake_dir)
        paths = lw.write(table, self._ROWS)
        return lw, lake_dir, paths

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_returns_one_path(self):
        _, _, paths = self._write()
        self.assertEqual(len(paths), 1)

    def test_path_is_relative(self):
        _, _, paths = self._write()
        self.assertFalse(Path(paths[0]).is_absolute())

    def test_path_starts_with_lake(self):
        _, _, paths = self._write()
        self.assertTrue(paths[0].startswith("lake/"))

    def test_path_contains_table_name(self):
        _, _, paths = self._write("customers")
        self.assertIn("customers", paths[0])

    def test_path_contains_date_partition(self):
        _, _, paths = self._write()
        self.assertRegex(paths[0], r"date=\d{4}-\d{2}-\d{2}")

    def test_path_ends_with_data_jsonl(self):
        _, _, paths = self._write()
        self.assertTrue(paths[0].endswith("data.jsonl"))

    def test_file_exists_on_disk(self):
        _, lake_dir, paths = self._write()
        out = lake_dir.parent / paths[0]
        self.assertTrue(out.exists())

    def test_file_has_correct_line_count(self):
        _, lake_dir, paths = self._write()
        out = lake_dir.parent / paths[0]
        lines = [l for l in out.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), len(self._ROWS))

    def test_each_line_is_valid_json(self):
        _, lake_dir, paths = self._write()
        out = lake_dir.parent / paths[0]
        for line in out.read_text().splitlines():
            if line.strip():
                obj = json.loads(line)
                self.assertIsInstance(obj, dict)

    def test_row_content_round_trips(self):
        _, lake_dir, paths = self._write()
        out = lake_dir.parent / paths[0]
        written = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
        self.assertEqual(written[0]["id"], 1)
        self.assertEqual(written[1]["title"], "Beta")


class TestLakeWriterIdempotency(SimpleTestCase):
    def test_rewrite_same_table_overwrites_not_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            lake_dir = Path(tmp) / "lake"
            lw = LakeWriter(lake_dir)
            rows = [{"id": 1, "title": "X"}]

            lw.write("cases", rows)
            lw.write("cases", rows)  # second write

            paths = lw.write("cases", rows)
            out = lake_dir.parent / paths[0]
            lines = [l for l in out.read_text().splitlines() if l.strip()]
            # Must still be 1 line, not 3
            self.assertEqual(len(lines), 1)

    def test_different_tables_write_to_separate_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            lake_dir = Path(tmp) / "lake"
            lw = LakeWriter(lake_dir)
            p_customers = lw.write("customers", [{"id": 1}])
            p_cases = lw.write("cases", [{"id": 2}])
            self.assertNotEqual(p_customers[0], p_cases[0])
