from __future__ import annotations

import hashlib
from datetime import datetime

from ...domain.entities import Case


class DjangoCaseRepository:
    def fetch_since(self, since: str) -> list[Case]:
        from ...infrastructure.models import Case as CaseModel

        cursor_dt = datetime.fromisoformat(since)
        qs = CaseModel.objects.filter(updated_at__gt=cursor_dt).order_by("updated_at")  # type: ignore[attr-defined]
        results: list[Case] = []
        for obj in qs:
            raw = {
                "id": obj.id,
                "customer_id": obj.customer_id,
                "title": obj.title,
                "description": obj.description,
                "status": obj.status,
                "created_at": obj.created_at.isoformat(),
                "updated_at": obj.updated_at.isoformat(),
            }
            results.append(
                Case(
                    id=obj.id,
                    customer_id=obj.customer_id,
                    title=obj.title,
                    description=obj.description,
                    status=obj.status,
                    updated_at=obj.updated_at.isoformat(),
                    raw=raw,
                )
            )
        return results

    def schema_fingerprint(self) -> str:
        from ...infrastructure.models import Case as CaseModel

        fields = sorted(
            f"{f.name}:{f.get_internal_type()}" for f in CaseModel._meta.concrete_fields
        )
        return hashlib.md5("|".join(fields).encode()).hexdigest()[:16]
