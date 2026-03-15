from __future__ import annotations

import dataclasses

from django.apps import apps
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["POST"])
def ingest(request):
    container = apps.get_app_config("ds")._container
    dry_run = request.GET.get("dry_run", "false").lower() == "true"
    try:
        manifest = container.ingest_use_case.execute(dry_run=dry_run)
        return JsonResponse(dataclasses.asdict(manifest))
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
