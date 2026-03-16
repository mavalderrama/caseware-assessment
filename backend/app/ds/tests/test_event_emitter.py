"""
FileAndSqsEventEmitter infrastructure tests.

All tests use SimpleTestCase (no database required).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from app.ds.infrastructure.event_emitter import FileAndSqsEventEmitter

EVENT_A = {
    "table": "cases",
    "run_id": "abc-123",
    "delta_row_count": 3,
    "lake_paths": ["lake/cases/date=2024-01-15/data.jsonl"],
    "checkpoint_after": "2024-01-15T10:00:00+00:00",
}
EVENT_B = {
    "table": "customers",
    "run_id": "abc-123",
    "delta_row_count": 1,
    "lake_paths": ["lake/customers/date=2024-01-15/data.jsonl"],
    "checkpoint_after": "2024-01-15T10:00:00+00:00",
}


class TestFileEventEmitter(SimpleTestCase):
    def _emitter(self, tmp: str) -> FileAndSqsEventEmitter:
        return FileAndSqsEventEmitter(
            events_dir=Path(tmp),
            queue_url="",
            sqs_client=None,
        )

    def test_emit_creates_events_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._emitter(tmp).emit(EVENT_A)
            self.assertTrue((Path(tmp) / "events.jsonl").exists())

    def test_emit_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "deep" / "events"
            FileAndSqsEventEmitter(nested, "", None).emit(EVENT_A)
            self.assertTrue((nested / "events.jsonl").exists())

    def test_emitted_line_is_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._emitter(tmp).emit(EVENT_A)
            line = (Path(tmp) / "events.jsonl").read_text().strip()
            obj = json.loads(line)
            self.assertEqual(obj["table"], "cases")

    def test_multiple_emits_append_separate_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = self._emitter(tmp)
            e.emit(EVENT_A)
            e.emit(EVENT_B)
            lines = [
                line
                for line in (Path(tmp) / "events.jsonl").read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(lines), 2)

    def test_all_emitted_events_present_in_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = self._emitter(tmp)
            e.emit(EVENT_A)
            e.emit(EVENT_B)
            tables = [
                json.loads(line)["table"]
                for line in (Path(tmp) / "events.jsonl").read_text().splitlines()
                if line.strip()
            ]
            self.assertIn("cases", tables)
            self.assertIn("customers", tables)

    def test_event_fields_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._emitter(tmp).emit(EVENT_A)
            obj = json.loads((Path(tmp) / "events.jsonl").read_text().strip())
            self.assertEqual(obj["run_id"], EVENT_A["run_id"])
            self.assertEqual(obj["delta_row_count"], EVENT_A["delta_row_count"])
            self.assertEqual(obj["lake_paths"], EVENT_A["lake_paths"])

    @patch("sys.stdout")
    def test_emit_prints_to_stdout(self, mock_stdout: MagicMock):
        with tempfile.TemporaryDirectory() as tmp:
            self._emitter(tmp).emit(EVENT_A)
        mock_stdout.write.assert_called()


class TestSqsEventEmitter(SimpleTestCase):
    def test_sqs_send_called_when_client_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            mock_sqs = MagicMock()
            emitter = FileAndSqsEventEmitter(Path(tmp), "http://sqs/queue", mock_sqs)
            emitter.emit(EVENT_A)
            mock_sqs.send_message.assert_called_once()
            call_kwargs = mock_sqs.send_message.call_args.kwargs
            self.assertEqual(call_kwargs["QueueUrl"], "http://sqs/queue")
            self.assertIn("cases", call_kwargs["MessageBody"])

    def test_sqs_failure_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken_sqs = MagicMock()
            broken_sqs.send_message.side_effect = Exception("connection refused")
            emitter = FileAndSqsEventEmitter(Path(tmp), "http://sqs/queue", broken_sqs)
            # Must not raise
            emitter.emit(EVENT_A)

    def test_no_sqs_call_when_queue_url_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            mock_sqs = MagicMock()
            emitter = FileAndSqsEventEmitter(Path(tmp), "", mock_sqs)
            emitter.emit(EVENT_A)
            mock_sqs.send_message.assert_not_called()

    def test_no_sqs_call_when_client_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Should not raise even with a queue URL but no client
            emitter = FileAndSqsEventEmitter(Path(tmp), "http://sqs/queue", None)
            emitter.emit(EVENT_A)
