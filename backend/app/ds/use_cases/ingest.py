from __future__ import annotations

import dataclasses
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..domain.entities import DeltaEvent, IngestManifest, TableManifest
from ..domain.ports import (
    CaseRepositoryPort,
    CheckpointStorePort,
    CustomerRepositoryPort,
    EventEmitterPort,
    LakeWriterPort,
    SearchIndexPort,
)


class IngestUseCase:
    def __init__(
        self,
        customer_repository: CustomerRepositoryPort,
        case_repository: CaseRepositoryPort,
        checkpoint_store: CheckpointStorePort,
        lake_writer: LakeWriterPort,
        event_emitter: EventEmitterPort,
        search_index: SearchIndexPort,
        lake_dir: Path,
    ) -> None:
        self._customer_repo = customer_repository
        self._case_repo = case_repository
        self._checkpoint_store = checkpoint_store
        self._lake_writer = lake_writer
        self._event_emitter = event_emitter
        self._search_index = search_index
        self._lake_dir = Path(lake_dir)

    def execute(self, dry_run: bool = False) -> IngestManifest:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        checkpoint = self._checkpoint_store.load()
        checkpoint_before = dict(checkpoint)

        # Fetch delta rows since the last checkpoint
        customers = self._customer_repo.fetch_since(
            checkpoint.get("customers", "1970-01-01T00:00:00+00:00")
        )
        cases = self._case_repo.fetch_since(checkpoint.get("cases", "1970-01-01T00:00:00+00:00"))

        # Schema fingerprints from repository metadata (not from row content)
        customer_fp = self._customer_repo.schema_fingerprint()
        case_fp = self._case_repo.schema_fingerprint()

        # Advance checkpoint cursors to the max updated_at seen
        new_customer_cursor = (
            max(c.updated_at for c in customers)
            if customers
            else checkpoint_before.get("customers")
        )
        new_case_cursor = (
            max(c.updated_at for c in cases) if cases else checkpoint_before.get("cases")
        )
        checkpoint_after = {
            "customers": new_customer_cursor,
            "cases": new_case_cursor,
        }

        customer_paths: list[str] = []
        case_paths: list[str] = []

        if not dry_run:
            # Write lake (overwrite = idempotent for same-day reruns)
            customer_paths = self._lake_writer.write("customers", [c.raw for c in customers])
            case_paths = self._lake_writer.write("cases", [c.raw for c in cases])

            # Emit one delta event per table
            for table, fp, delta_count, paths, cursor in [
                ("customers", customer_fp, len(customers), customer_paths, new_customer_cursor),
                ("cases", case_fp, len(cases), case_paths, new_case_cursor),
            ]:
                event = DeltaEvent(
                    table=table,
                    run_id=run_id,
                    schema_fingerprint=fp,
                    delta_row_count=delta_count,
                    lake_paths=paths,
                    checkpoint_after=cursor,
                )
                self._event_emitter.emit(dataclasses.asdict(event))

            # Advance checkpoint — only after both writes succeed
            self._checkpoint_store.save(checkpoint_after)

            # Rebuild search index from the full lake (all date partitions, deduplicated)
            self._search_index.rebuild_from_lake(self._lake_dir)

        finished_at = datetime.now(timezone.utc).isoformat()

        return IngestManifest(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            dry_run=dry_run,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
            tables={
                "customers": TableManifest(
                    row_count=len(customers),
                    lake_paths=customer_paths,
                    schema_fingerprint=customer_fp,
                ),
                "cases": TableManifest(
                    row_count=len(cases),
                    lake_paths=case_paths,
                    schema_fingerprint=case_fp,
                ),
            },
        )


def _schema_fingerprint_from_keys(row: dict) -> str:
    keys = sorted(row.keys())
    return hashlib.md5("|".join(keys).encode()).hexdigest()[:16]
