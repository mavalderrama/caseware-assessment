# datasearchpy

Incremental Postgres ingest → local JSONL data lake + deterministic similarity search.

---

## Quick start

```bash
# 1. Bring up Postgres (pgvector) + LocalStack (SQS) + Django
docker compose up --build -d

# 2. Wait for health check to pass
curl -s http://localhost:8000/health/
# {"status": "ok"}
```

---

## Endpoints

### `GET /health/`
```bash
curl -s http://localhost:8000/health/
```

### `POST /ingest`
Ingests rows updated since the last checkpoint, writes JSONL to `./lake/`, emits delta events, advances the checkpoint.

```bash
# Normal ingest
curl -s -X POST http://localhost:8000/ingest | python3 -m json.tool

# Dry run — compute delta without writing or advancing checkpoint
curl -s -X POST "http://localhost:8000/ingest?dry_run=true" | python3 -m json.tool
```

Example response:
```json
{
  "run_id": "3e4a7b...",
  "started_at": "2024-01-15T10:00:00+00:00",
  "finished_at": "2024-01-15T10:00:01+00:00",
  "dry_run": false,
  "checkpoint_before": {"customers": "1970-01-01T00:00:00+00:00", "cases": "1970-01-01T00:00:00+00:00"},
  "checkpoint_after":  {"customers": "2024-01-15T09:50:00+00:00", "cases": "2024-01-15T09:55:00+00:00"},
  "tables": {
    "customers": {"row_count": 3, "lake_paths": ["lake/customers/date=2024-01-15/data.jsonl"], "schema_fingerprint": "aabb1122..."},
    "cases":     {"row_count": 5, "lake_paths": ["lake/cases/date=2024-01-15/data.jsonl"],     "schema_fingerprint": "ccdd3344..."}
  }
}
```

### `POST /search`
Returns top-k cases ranked by similarity to the query. The index is built from the lake on startup and refreshed after each successful ingest.

```bash
curl -s -X POST http://localhost:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "login failure after password reset", "top_k": 3}' \
  | python3 -m json.tool
```

Example response:
```json
[
  {"case_id": 1, "score": 0.92, "title": "Login failure after password reset", "status": "open"},
  {"case_id": 5, "score": 0.71, "title": "Password reset link expired",         "status": "open"},
  {"case_id": 3, "score": 0.48, "title": "Dashboard slow to load",              "status": "open"}
]
```

---

## Running tests

```bash
cd backend
.venv/bin/python manage.py test app.ds
```

All 17 tests use `SimpleTestCase` (no Postgres or SentenceTransformer required).

## Linting

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

---

## Data layout

```
lake/
  customers/date=YYYY-MM-DD/data.jsonl   # overwritten per run per day
  cases/date=YYYY-MM-DD/data.jsonl
state/
  checkpoint.json                         # atomic cursor; only advances on success
events/
  events.jsonl                            # one delta event appended per table per run
```

---

## Key assumptions and tradeoffs

| Decision | Rationale |
|---|---|
| SentenceTransformer (`all-MiniLM-L6-v2`) | Real embeddings for production quality; hash-based is allowed by challenge but this is better |
| `os.replace()` for checkpoint atomicity | POSIX-atomic rename; crash mid-write can't corrupt the checkpoint |
| Lake writes in `'w'` mode | Overwrite = idempotent for same-day re-runs; no duplicate rows |
| `updated_at__gt` (strict greater-than) | Prevents re-fetching the exact boundary row on the next run |
| Rebuild index from full lake after ingest | Index reflects all historical data, not just the current delta |
| `threading.RLock` on index entries | Dev server spawns threads; rebuild and search must not race |
| SQS emit wrapped in `try/except` | LocalStack not guaranteed in all environments; lake + stdout always succeed |
| `SimpleTestCase` for all tests | Tests run without Postgres; all ports replaced with in-memory fakes |
