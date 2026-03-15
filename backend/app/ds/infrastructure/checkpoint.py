from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_CURSOR = "1970-01-01T00:00:00+00:00"
DEFAULT_CHECKPOINT: dict[str, str] = {
    "customers": DEFAULT_CURSOR,
    "cases": DEFAULT_CURSOR,
}


class FileCheckpointStore:
    def __init__(self, state_dir: Path) -> None:
        self._path = Path(state_dir) / "checkpoint.json"

    def load(self) -> dict[str, str]:
        if not self._path.exists():
            return dict(DEFAULT_CHECKPOINT)
        with open(self._path) as f:
            return json.load(f)

    def save(self, checkpoint: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to tmp then rename (os.replace is POSIX-atomic)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(checkpoint, f, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
