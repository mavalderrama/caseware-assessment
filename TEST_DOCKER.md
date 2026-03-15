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
| `manage.py migrate` runs | `web` | ~5 s |

Wait until you see:

```
web-1  | Starting development server at http://0.0.0.0:8000/
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
# Django health endpoint
curl -s http://localhost:8000/health/ | python3 -m json.tool
```

Expected:

```json
{"status": "ok"}
```

---

## 3. Seed the database

The database starts empty. Insert rows so ingest has data to pick up.

```bash
docker compose exec db psql -U datasearch -d datasearch -c "
INSERT INTO customers (name, email, updated_at, created_at)
VALUES
  ('Alice',   'alice@example.com',   now(), now()),
  ('Bob',     'bob@example.com',     now(), now()),
  ('Charlie', 'charlie@example.com', now(), now())
ON CONFLICT (email) DO NOTHING;

INSERT INTO cases (customer_id, title, description, status, updated_at, created_at)
VALUES
  (1, 'Login broken',          'Cannot log in after password reset',   'open',     now(), now()),
  (1, 'Invoice missing',       'Invoice #1042 not in billing portal',  'closed',   now(), now()),
  (2, 'Slow dashboard',        'Dashboard takes 30s to load',          'open',     now(), now()),
  (2, 'Wrong timezone',        'Timestamps show UTC instead of EST',   'resolved', now(), now()),
  (3, 'Export CSV fails',      'CSV export returns 500 error',         'open',     now(), now()),
  (3, 'Missing notification',  'Email alerts not sent on ticket close','open',     now(), now())
ON CONFLICT DO NOTHING;
"
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
  "started_at": "2026-03-15T10:00:00.000000",
  "finished_at": "2026-03-15T10:00:01.234567",
  "dry_run": false,
  "checkpoint_before": {"customers": "1970-01-01T00:00:00", "cases": "1970-01-01T00:00:00"},
  "checkpoint_after":  {"customers": "2026-03-15T10:00:00.123456", "cases": "2026-03-15T10:00:00.654321"},
  "tables": {
    "customers": {"row_count": 3, "lake_paths": ["lake/customers/date=2026-03-15/data.jsonl"], "schema_fingerprint": "..."},
    "cases":     {"row_count": 6, "lake_paths": ["lake/cases/date=2026-03-15/data.jsonl"],     "schema_fingerprint": "..."}
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

### 4d. Ingest incremental update

Insert one new case and re-ingest:

```bash
docker compose exec db psql -U datasearch -d datasearch -c "
INSERT INTO cases (customer_id, title, description, status, updated_at, created_at)
VALUES (1, 'New urgent issue', 'Production is down', 'open', now(), now());
"

curl -s -X POST http://localhost:8000/ingest | python3 -m json.tool
```

Expected: `cases.row_count` is `1`; `customers.row_count` is `0` (no customers changed).

---

## 5. POST /search

Requires at least one successful ingest first (index is built from the lake on startup and refreshed after each ingest).

```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "login password", "top_k": 3}' \
  | python3 -m json.tool
```

Expected response (ordered by score descending, deterministic):

```json
[
  {"case_id": 1, "score": 0.843, "title": "Login broken",   "status": "open"},
  {"case_id": 3, "score": 0.512, "title": "Slow dashboard", "status": "open"},
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

## 6. Verify LocalStack resources

```bash
# List S3 lake bucket contents
docker compose exec localstack awslocal s3 ls s3://datasearchpy-lake --recursive

# Check SQS for delta event messages
docker compose exec localstack awslocal sqs receive-message \
  --queue-url http://localhost:4566/000000000000/datasearchpy-events \
  --max-number-of-messages 10 \
  | python3 -m json.tool
```

Each SQS message body contains the same delta event shape as `events/events.jsonl`.

---

## 7. Run the automated test suite

```bash
docker compose exec web python manage.py test app.ds
```

Tests cover checkpoint correctness (advance only on success, idempotency) and search determinism.

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
