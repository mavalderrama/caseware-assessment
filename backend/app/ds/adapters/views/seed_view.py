from __future__ import annotations

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

SAMPLE_CUSTOMERS = [
    {"name": "Acme Corp",       "email": "support@acme.com"},
    {"name": "Globex Inc",      "email": "help@globex.com"},
    {"name": "Initech LLC",     "email": "contact@initech.com"},
    {"name": "Umbrella Ltd",    "email": "info@umbrella.com"},
    {"name": "Hooli Systems",   "email": "care@hooli.com"},
]

SAMPLE_CASES = [
    # Acme Corp (customer index 0)
    {"customer_idx": 0, "title": "Login broken after password reset",       "description": "Users cannot log in after resetting their password. The reset link works but subsequent login attempts fail with 401.",          "status": "open"},
    {"customer_idx": 0, "title": "Invoice #1042 missing from billing portal","description": "Invoice issued on the 1st is not visible in the billing portal. Payment was processed but no PDF is available.",                "status": "closed"},
    {"customer_idx": 0, "title": "API rate limit too restrictive",           "description": "The 100 req/min limit is blocking our batch job. We need at least 500 req/min for nightly reconciliation.",                       "status": "open"},
    # Globex Inc (customer index 1)
    {"customer_idx": 1, "title": "Dashboard loads in 30+ seconds",          "description": "The main analytics dashboard is extremely slow. Network tab shows a single query taking 28 s. Happens only for large date ranges.","status": "open"},
    {"customer_idx": 1, "title": "CSV export returns 500 error",            "description": "Exporting more than 10 000 rows via the CSV button returns a 500. Smaller exports work fine.",                                    "status": "open"},
    {"customer_idx": 1, "title": "Email alerts not sent on ticket close",   "description": "Notification emails are not delivered when a support ticket transitions to closed. Slack webhook fires correctly.",                 "status": "resolved"},
    # Initech LLC (customer index 2)
    {"customer_idx": 2, "title": "Timestamps display UTC instead of EST",   "description": "All timestamps in the UI show UTC. User timezone is set to America/New_York in profile settings but is being ignored.",           "status": "open"},
    {"customer_idx": 2, "title": "Two-factor authentication not working",   "description": "TOTP codes from Google Authenticator are rejected. The issue started after our SSO migration last Tuesday.",                       "status": "open"},
    {"customer_idx": 2, "title": "Bulk user import fails on row 47",        "description": "Uploading a 200-row CSV for bulk user creation fails silently at row 47. No error message is shown in the UI.",                    "status": "closed"},
    # Umbrella Ltd (customer index 3)
    {"customer_idx": 3, "title": "Payment gateway timeout on checkout",     "description": "Stripe webhook responses are timing out during peak hours (18:00–20:00 UTC). Transactions eventually complete but orders are duplicated.", "status": "open"},
    {"customer_idx": 3, "title": "SSO redirect loop after session expiry",  "description": "After an idle session expires, clicking login triggers an infinite redirect loop between our app and the IdP.",                    "status": "open"},
    {"customer_idx": 3, "title": "Search returns stale results",            "description": "Full-text search still returns deleted records. A re-index was triggered 2 days ago but the problem persists.",                    "status": "resolved"},
    # Hooli Systems (customer index 4)
    {"customer_idx": 4, "title": "Webhook signature validation failing",    "description": "Our endpoint rejects incoming webhooks with 403. We verified the secret is correct. Issue appeared after a key rotation.",         "status": "open"},
    {"customer_idx": 4, "title": "Mobile app crashes on iOS 18.3",         "description": "The iOS client crashes immediately on launch for users on iOS 18.3. Earlier versions are unaffected. Crashlytics report attached.", "status": "open"},
    {"customer_idx": 4, "title": "Data export missing custom fields",       "description": "Exported XLSX files omit columns for custom fields added after January 2026. Standard fields export correctly.",                   "status": "closed"},
]


@csrf_exempt
@require_http_methods(["POST"])
def seed(request):
    from django.apps import apps

    from ...infrastructure.models import Case as CaseModel
    from ...infrastructure.models import Customer as CustomerModel
    from ...infrastructure.search_index import PgvectorSearchIndex

    container = apps.get_app_config("ds")._container
    model = PgvectorSearchIndex._get_model(container.search_index._model_name)

    # Pre-compute embeddings for all cases in one batch
    texts = [
        f"{c['title']} {c['description']} {c['status']}".strip()
        for c in SAMPLE_CASES
    ]
    embeddings = model.encode(texts, normalize_embeddings=True)

    created_customers = 0
    updated_customers = 0
    created_cases = 0
    updated_cases = 0

    with transaction.atomic():
        customer_objs: list[CustomerModel] = []
        for c in SAMPLE_CUSTOMERS:
            obj, created = CustomerModel.objects.update_or_create(
                email=c["email"],
                defaults={"name": c["name"]},
            )
            customer_objs.append(obj)
            if created:
                created_customers += 1
            else:
                updated_customers += 1

        for case, embedding in zip(SAMPLE_CASES, embeddings):
            customer = customer_objs[case["customer_idx"]]
            _, created = CaseModel.objects.update_or_create(
                customer=customer,
                title=case["title"],
                defaults={
                    "description": case["description"],
                    "status": case["status"],
                    "embedding": embedding.tolist(),
                },
            )
            if created:
                created_cases += 1
            else:
                updated_cases += 1

    return JsonResponse({
        "customers": {"created": created_customers, "updated": updated_customers},
        "cases":     {"created": created_cases,     "updated": updated_cases},
    }, status=201)
