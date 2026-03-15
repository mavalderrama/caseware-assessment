from __future__ import annotations

import hashlib
from datetime import datetime

from ...domain.entities import Customer


class DjangoCustomerRepository:
    def fetch_since(self, since: str) -> list[Customer]:
        from ...infrastructure.models import Customer as CustomerModel

        cursor_dt = datetime.fromisoformat(since)
        qs = CustomerModel.objects.filter(updated_at__gt=cursor_dt).order_by("updated_at")
        results: list[Customer] = []
        for obj in qs:
            raw = {
                "id": obj.id,
                "name": obj.name,
                "email": obj.email,
                "created_at": obj.created_at.isoformat(),
                "updated_at": obj.updated_at.isoformat(),
            }
            results.append(
                Customer(
                    id=obj.id,
                    name=obj.name,
                    email=obj.email,
                    updated_at=obj.updated_at.isoformat(),
                    raw=raw,
                )
            )
        return results

    def schema_fingerprint(self) -> str:
        from ...infrastructure.models import Customer as CustomerModel

        fields = sorted(
            f"{f.name}:{f.get_internal_type()}" for f in CustomerModel._meta.concrete_fields
        )
        return hashlib.md5("|".join(fields).encode()).hexdigest()[:16]
