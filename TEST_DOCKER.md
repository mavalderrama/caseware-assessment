# Docker Compose — Spin-up & Endpoint Testing

## Prerequisites

- Docker Engine ≥ 24 with the Compose plugin (`docker compose version`)
- Ports 5432, 4566, and 8000 free on the host

---

## 1. Start the stack

```bash
docker compose up --build
```

**What happens on first boot:**

| Step | Service | Time |
|---|---|---|
| Postgres initialises + pgvector extension | `db` | ~5 s |
| LocalStack starts, init script creates SQS queues + S3 bucket | `localstack` | ~15–20 s |
| Django image builds + deps installed | `web` | ~3–5 min (PyTorch/sentence-transformers) |
| `all-MiniLM-L6-v2` model downloads (~90 MB, cached to `model_cache` volume) | `web` | ~30 s (first run only) |
| `manage.py migrate` runs, gunicorn starts | `web` | ~5 s |

Wait until you see:

```
web-1  | [INFO] Listening at: http://0.0.0.0:8000
web-1  | [INFO] Worker booted (pid: ...)
```

To run detached:

```bash
docker compose up --build -d
docker compose logs -f web   # tail app logs
```

---

## 2. Verify all services are healthy

```bash
docker compose ps
```

Expected: all three services show `healthy` or `running`.

```bash
curl -s http://localhost:8000/health/ | python3 -m json.tool
```

Expected:

```json
{"status": "ok"}
```

---

## 3. Seed the database — Batch 1 (baseline)

Use the built-in seed endpoint to insert sample data. Batch 1 loads 5 customers and 15 cases covering a range of statuses and topics.

```bash
curl -s -X POST http://localhost:8000/seed | python3 -m json.tool
```

Expected:

```json
{
  "customers": {"created": 5, "updated": 0},
  "cases":     {"created": 15, "updated": 0}
}
```

---

## 4. POST /ingest

### 4a. Real ingest (writes lake + advances checkpoint)

```bash
curl -s -X POST http://localhost:8000/ingest | python3 -m json.tool
```

Expected response shape:

```json
{
  "run_id": "a1b2c3d4-...",
  "started_at": "2026-03-15T10:00:00.000000+00:00",
  "finished_at": "2026-03-15T10:00:01.234567+00:00",
  "dry_run": false,
  "checkpoint_before": {"customers": "1970-01-01T00:00:00+00:00", "cases": "1970-01-01T00:00:00+00:00"},
  "checkpoint_after":  {"customers": "2026-03-15T10:00:00.123456+00:00", "cases": "2026-03-15T10:00:00.654321+00:00"},
  "tables": {
    "customers": {"row_count": 5,  "lake_paths": ["lake/customers/date=2026-03-15/data.jsonl"], "schema_fingerprint": "..."},
    "cases":     {"row_count": 15, "lake_paths": ["lake/cases/date=2026-03-15/data.jsonl"],     "schema_fingerprint": "..."}
  }
}
```

Verify lake files were written:

```bash
cat lake/customers/date=$(date +%Y-%m-%d)/data.jsonl
cat lake/cases/date=$(date +%Y-%m-%d)/data.jsonl
```

Each line is a valid JSON object (one row per line).

Verify delta events were appended:

```bash
cat events/events.jsonl
```

Expected: two lines (one per table), each containing `table`, `run_id`, `schema_fingerprint`, `delta_row_count`, `lake_paths`, `checkpoint_after`.

### 4b. Idempotency check — re-run with no DB changes

```bash
curl -s -X POST http://localhost:8000/ingest | python3 -m json.tool
```

Expected: `row_count` is `0` for both tables; `checkpoint_after` equals `checkpoint_before`; no new lines in `events/events.jsonl`.

Lake files are **overwritten** (not appended), so line counts stay the same:

```bash
wc -l lake/customers/date=$(date +%Y-%m-%d)/data.jsonl
wc -l lake/cases/date=$(date +%Y-%m-%d)/data.jsonl
```

### 4c. Dry run — computes but writes nothing

```bash
curl -s -X POST "http://localhost:8000/ingest?dry_run=true" | python3 -m json.tool
```

Expected: `"dry_run": true`; `checkpoint_after` equals `checkpoint_before` (no advancement); no changes to `state/checkpoint.json` or `events/events.jsonl`.

### 4d. Ingest incremental update — Batch 2

Seed the second batch of sample data (3 new customers, 9 new cases — all with fresh `updated_at` timestamps):

```bash
curl -s -X POST "http://localhost:8000/seed?batch=2" | python3 -m json.tool
```

Expected:

```json
{
  "customers": {"created": 3, "updated": 0},
  "cases":     {"created": 9, "updated": 0}
}
```

Now ingest the delta:

```bash
curl -s -X POST http://localhost:8000/ingest | python3 -m json.tool
```

Expected: `customers.row_count` is `3`; `cases.row_count` is `9`. The checkpoint advances to the batch-2 timestamps. A new or overwritten lake file is written for today's date.

---

## 5. POST /search

Requires at least one successful ingest (index is built from the lake on startup and refreshed after each ingest).

```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "login password", "top_k": 3}' \
  | python3 -m json.tool
```

Expected response (ordered by score descending, deterministic):

```json
[
  {"case_id": 1, "score": 0.843, "title": "Login broken after password reset", "status": "open"},
  ...
]
```

**Determinism check** — same query must always return the same ordered results:

```bash
R1=$(curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "billing invoice", "top_k": 5}')

R2=$(curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "billing invoice", "top_k": 5}')

[ "$R1" = "$R2" ] && echo "PASS: deterministic" || echo "FAIL: non-deterministic"
```

**Validation checks:**

```bash
# Missing query — expects 400
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"top_k": 5}'
# → 400

# Invalid JSON — expects 400
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d 'not-json'
# → 400
```

---

## 6. Test SQS and S3 (LocalStack)

### 6a. Verify LocalStack resources were created

```bash
# List SQS queues
docker compose exec localstack awslocal sqs list-queues

# List S3 buckets
docker compose exec localstack awslocal s3 ls
```

Expected queues: `datasearchpy-events` and `datasearchpy-events-dlq`.
Expected bucket: `datasearchpy-lake`.

### 6b. SQS — delta events

The app publishes one SQS message per table after each successful ingest. Run a seed + ingest first if you haven't already:

```bash
curl -s -X POST http://localhost:8000/seed | python3 -m json.tool
curl -s -X POST http://localhost:8000/ingest | python3 -m json.tool
```

Read the messages from the queue:

```bash
docker compose exec localstack awslocal sqs receive-message \
  --queue-url http://localhost:4566/000000000000/datasearchpy-events \
  --max-number-of-messages 10 \
  | python3 -m json.tool
```

Expected: two messages (one per table). Each `MessageBody` is a JSON string matching the delta event shape:

```json
{
  "table": "cases",
  "run_id": "...",
  "schema_fingerprint": "...",
  "delta_row_count": 15,
  "lake_paths": ["lake/cases/date=2026-03-16/data.jsonl"],
  "checkpoint_after": "2026-03-16T..."
}
```

To parse a message body inline:

```bash
docker compose exec localstack awslocal sqs receive-message \
  --queue-url http://localhost:4566/000000000000/datasearchpy-events \
  --max-number-of-messages 1 \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
for msg in data.get('Messages', []):
    print(json.dumps(json.loads(msg['MessageBody']), indent=2))
"
```

**Verify the DLQ is empty** (messages only land here after 3 failed processing attempts):

```bash
docker compose exec localstack awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/datasearchpy-events-dlq \
  --attribute-names ApproximateNumberOfMessages
```

Expected: `"ApproximateNumberOfMessages": "0"`.

**Check queue depth** (how many unprocessed messages are waiting):

```bash
docker compose exec localstack awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/datasearchpy-events \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```

> Note: `receive-message` makes messages invisible for 300 s (the `VisibilityTimeout`). If you call it multiple times without deleting messages, subsequent calls may return empty until the timeout expires. To reset, purge the queue:
>
> ```bash
> docker compose exec localstack awslocal sqs purge-queue \
>   --queue-url http://localhost:4566/000000000000/datasearchpy-events
> ```

### 6c. S3 — lake bucket

The `datasearchpy-lake` bucket is provisioned and versioning is enabled, but the current app writes the lake to the local bind-mounted directory (`./lake/`) rather than uploading to S3. The bucket is ready for a future S3-backed lake implementation.

Verify the bucket and its versioning config:

```bash
# Confirm bucket exists
docker compose exec localstack awslocal s3 ls

# Confirm versioning is enabled
docker compose exec localstack awslocal s3api get-bucket-versioning \
  --bucket datasearchpy-lake
```

Expected versioning output: `{"Status": "Enabled"}`.

To manually upload the local lake files and verify round-trip:

```bash
# Upload today's lake files
docker compose exec localstack awslocal s3 sync /app/lake s3://datasearchpy-lake/lake

# List what was uploaded
docker compose exec localstack awslocal s3 ls s3://datasearchpy-lake/lake --recursive
```

---

## 7. Run the automated test suite

```bash
docker compose exec web pytest
```

Tests cover checkpoint correctness, idempotency, delta event shape, manifest completeness, lake writer, checkpoint store, and event emitter.

---

## 8. Tear down

```bash
# Stop and remove containers + networks (keep volumes)
docker compose down

# Full reset including all volumes (clears Postgres data, LocalStack state, model cache)
docker compose down -v

# Also clear local data dirs
rm -rf state/checkpoint.json events/events.jsonl lake/
```
