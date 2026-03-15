from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class FileAndSqsEventEmitter:
    def __init__(
        self,
        events_dir: Path,
        queue_url: str,
        sqs_client: Any = None,
    ) -> None:
        self._events_path = Path(events_dir) / "events.jsonl"
        self._queue_url = queue_url
        self._sqs_client = sqs_client

    def emit(self, event: dict) -> None:
        line = json.dumps(event, default=str)

        # stdout
        print(line, flush=True, file=sys.stdout)

        # Append to events file
        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._events_path, "a") as f:
            f.write(line + "\n")

        # SQS — best-effort; failure does not affect ingest outcome
        if self._sqs_client and self._queue_url:
            try:
                self._sqs_client.send_message(
                    QueueUrl=self._queue_url,
                    MessageBody=line,
                )
            except Exception:
                pass
