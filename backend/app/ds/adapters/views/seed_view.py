from __future__ import annotations

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# ── Batch 1 — baseline dataset ────────────────────────────────────────────────
# Seed this first, then call POST /ingest to establish the checkpoint watermark.

SAMPLE_CUSTOMERS_1 = [
    {"name": "Acme Corp", "email": "support@acme.com"},
    {"name": "Globex Inc", "email": "help@globex.com"},
    {"name": "Initech LLC", "email": "contact@initech.com"},
    {"name": "Umbrella Ltd", "email": "info@umbrella.com"},
    {"name": "Hooli Systems", "email": "care@hooli.com"},
]

SAMPLE_CASES_1 = [
    # Acme Corp (index 0)
    {
        "customer_idx": 0,
        "title": "Login broken after password reset",
        "description": "Users cannot log in after resetting their password. The reset link works but subsequent login attempts fail with 401.",
        "status": "open",
    },
    {
        "customer_idx": 0,
        "title": "Invoice #1042 missing from billing portal",
        "description": "Invoice issued on the 1st is not visible in the billing portal. Payment was processed but no PDF is available.",
        "status": "closed",
    },
    {
        "customer_idx": 0,
        "title": "API rate limit too restrictive",
        "description": "The 100 req/min limit is blocking our batch job. We need at least 500 req/min for nightly reconciliation.",
        "status": "open",
    },
    # Globex Inc (index 1)
    {
        "customer_idx": 1,
        "title": "Dashboard loads in 30+ seconds",
        "description": "The main analytics dashboard is extremely slow. Network tab shows a single query taking 28 s. Happens only for large date ranges.",
        "status": "open",
    },
    {
        "customer_idx": 1,
        "title": "CSV export returns 500 error",
        "description": "Exporting more than 10 000 rows via the CSV button returns a 500. Smaller exports work fine.",
        "status": "open",
    },
    {
        "customer_idx": 1,
        "title": "Email alerts not sent on ticket close",
        "description": "Notification emails are not delivered when a support ticket transitions to closed. Slack webhook fires correctly.",
        "status": "resolved",
    },
    # Initech LLC (index 2)
    {
        "customer_idx": 2,
        "title": "Timestamps display UTC instead of EST",
        "description": "All timestamps in the UI show UTC. User timezone is set to America/New_York in profile settings but is being ignored.",
        "status": "open",
    },
    {
        "customer_idx": 2,
        "title": "Two-factor authentication not working",
        "description": "TOTP codes from Google Authenticator are rejected. The issue started after our SSO migration last Tuesday.",
        "status": "open",
    },
    {
        "customer_idx": 2,
        "title": "Bulk user import fails on row 47",
        "description": "Uploading a 200-row CSV for bulk user creation fails silently at row 47. No error message is shown in the UI.",
        "status": "closed",
    },
    # Umbrella Ltd (index 3)
    {
        "customer_idx": 3,
        "title": "Payment gateway timeout on checkout",
        "description": "Stripe webhook responses are timing out during peak hours (18:00–20:00 UTC). Transactions eventually complete but orders are duplicated.",
        "status": "open",
    },
    {
        "customer_idx": 3,
        "title": "SSO redirect loop after session expiry",
        "description": "After an idle session expires, clicking login triggers an infinite redirect loop between our app and the IdP.",
        "status": "open",
    },
    {
        "customer_idx": 3,
        "title": "Search returns stale results",
        "description": "Full-text search still returns deleted records. A re-index was triggered 2 days ago but the problem persists.",
        "status": "resolved",
    },
    # Hooli Systems (index 4)
    {
        "customer_idx": 4,
        "title": "Webhook signature validation failing",
        "description": "Our endpoint rejects incoming webhooks with 403. We verified the secret is correct. Issue appeared after a key rotation.",
        "status": "open",
    },
    {
        "customer_idx": 4,
        "title": "Mobile app crashes on iOS 18.3",
        "description": "The iOS client crashes immediately on launch for users on iOS 18.3. Earlier versions are unaffected. Crashlytics report attached.",
        "status": "open",
    },
    {
        "customer_idx": 4,
        "title": "Data export missing custom fields",
        "description": "Exported XLSX files omit columns for custom fields added after January 2026. Standard fields export correctly.",
        "status": "closed",
    },
]

# ── Batch 2 — incremental delta ───────────────────────────────────────────────
# Seed this AFTER running POST /ingest on batch 1.
# These are entirely new customers and cases (distinct emails / titles),
# so the next /ingest will pick them up as a clean delta and advance the
# checkpoint to their updated_at timestamps.

SAMPLE_CUSTOMERS_2 = [
    {"name": "Massive Dynamic", "email": "support@massivedynamic.com"},
    {"name": "Cyberdyne Corp", "email": "help@cyberdyne.com"},
    {"name": "Soylent Systems", "email": "contact@soylent.com"},
]

SAMPLE_CASES_2 = [
    # Massive Dynamic (index 0)
    {
        "customer_idx": 0,
        "title": "Report scheduler skips weekends",
        "description": "Scheduled PDF reports set to run daily are not generated on Saturdays or Sundays despite the cron expression being '0 8 * * *'.",
        "status": "open",
    },
    {
        "customer_idx": 0,
        "title": "Audit log entries missing user ID",
        "description": "Audit trail events fired from the background worker omit the actor user_id field, making compliance review impossible.",
        "status": "open",
    },
    {
        "customer_idx": 0,
        "title": "Dark mode breaks data table contrast",
        "description": "In dark mode, table row text renders as #1a1a1a on a #1e1e1e background. Affects all pages with DataGrid components.",
        "status": "open",
    },
    # Cyberdyne Corp (index 1)
    {
        "customer_idx": 1,
        "title": "Multi-region failover not triggering",
        "description": "Health check endpoint returns 200 from the primary region even during a simulated outage. Failover to eu-west-1 never activates.",
        "status": "open",
    },
    {
        "customer_idx": 1,
        "title": "Object storage presigned URLs expire early",
        "description": "Presigned S3 URLs sent via email expire after 5 minutes instead of the configured 24 hours. Bucket policy looks correct.",
        "status": "open",
    },
    {
        "customer_idx": 1,
        "title": "GraphQL subscriptions drop after 60s",
        "description": "WebSocket connections for GraphQL subscriptions are silently terminated after exactly 60 seconds. The ALB idle timeout is 120s.",
        "status": "resolved",
    },
    # Soylent Systems (index 2)
    {
        "customer_idx": 2,
        "title": "Pagination breaks on filtered result sets",
        "description": "Applying a status filter and navigating to page 3 returns the same rows as page 1. Offset calculation ignores active filters.",
        "status": "open",
    },
    {
        "customer_idx": 2,
        "title": "PDF invoice font renders as boxes on Linux",
        "description": "Invoices generated on the server display correctly on macOS but show empty boxes instead of characters when opened on Linux.",
        "status": "open",
    },
    {
        "customer_idx": 2,
        "title": "Session token not invalidated on logout",
        "description": "After clicking logout the JWT remains valid for its full TTL. Re-submitting the token to /api/me returns 200 instead of 401.",
        "status": "open",
    },
]


def _upsert_batch(customers: list[dict], cases: list[dict]) -> dict:
    from django.apps import apps

    from ...infrastructure.models import Case as CaseModel
    from ...infrastructure.models import Customer as CustomerModel
    from ...infrastructure.search_index import PgvectorSearchIndex

    container = apps.get_app_config("ds")._container  # type: ignore[attr-defined]
    model = PgvectorSearchIndex._get_model(container.search_index._model_name)

    texts = [f"{c['title']} {c['description']} {c['status']}".strip() for c in cases]
    embeddings = model.encode(texts, normalize_embeddings=True)

    created_customers = updated_customers = created_cases = updated_cases = 0

    with transaction.atomic():
        customer_objs: list[CustomerModel] = []
        for c in customers:
            obj, created = CustomerModel.objects.update_or_create(  # type: ignore[attr-defined]
                email=c["email"],
                defaults={"name": c["name"]},
            )
            customer_objs.append(obj)
            if created:
                created_customers += 1
            else:
                updated_customers += 1

        for case, embedding in zip(cases, embeddings):
            customer = customer_objs[case["customer_idx"]]
            _, created = CaseModel.objects.update_or_create(  # type: ignore[attr-defined]
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

    return {
        "customers": {"created": created_customers, "updated": updated_customers},
        "cases": {"created": created_cases, "updated": updated_cases},
    }


@csrf_exempt
@require_http_methods(["POST"])
def seed(request):
    batch = request.GET.get("batch", "1")
    if batch == "2":
        result = _upsert_batch(SAMPLE_CUSTOMERS_2, SAMPLE_CASES_2)
    else:
        result = _upsert_batch(SAMPLE_CUSTOMERS_1, SAMPLE_CASES_1)
    return JsonResponse(result, status=201)
