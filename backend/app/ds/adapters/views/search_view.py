from __future__ import annotations

import dataclasses
import json

from django.apps import apps
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["POST"])
def search(request):
    container = apps.get_app_config("ds")._container  # type: ignore[attr-defined]
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"error": f"Invalid JSON: {exc}"}, status=400)

    query = body.get("query", "")
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    top_k = int(body.get("top_k", 5))
    results = container.search_use_case.execute(query=query, top_k=top_k)
    return JsonResponse([dataclasses.asdict(r) for r in results], safe=False)
