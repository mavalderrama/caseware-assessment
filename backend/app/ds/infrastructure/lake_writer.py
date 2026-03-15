from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class LakeWriter:
    def __init__(self, lake_dir: Path) -> None:
        self._lake_dir = Path(lake_dir)

    def write(self, table: str, rows: list[dict]) -> list[str]:
        if not rows:
            return []
        today = date.today().isoformat()
        out_dir = self._lake_dir / table / f"date={today}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "data.jsonl"
        # Overwrite for idempotency: re-running with no new rows produces the same file
        with open(out_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, default=str) + "\n")
        return [str(out_path.relative_to(self._lake_dir.parent))]
