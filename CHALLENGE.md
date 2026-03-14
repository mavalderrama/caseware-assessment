# Senior Software Data Developer: Mini Data Interop +
Event Sync + AI-Ready Search

## Your task
Build a small service that:
1. Incrementally ingests changes from Postgres
2. Writes the ingested data to a local “data lake” folder as JSONL
3. Emits delta events per table
4. Exposes a deterministic “vector-like” search endpoint over cases

## Requirements
1. Incremental ingest: Implement a checkpoint/watermark mechanism based on a timestamp column (use
   updated_at).
   - The system must keep a checkpoint in a local file, e.g.:
     - ./state/checkpoint.json
   - Each ingest run loads rows updated since the last checkpoint for:
     - customers
     - cases
   - Checkpoint must advance only if the run succeeds end-to-end (no partial progress).

### Endpoint
POST /ingest?dry_run=true|false
- If dry_run=true:
  - Compute what would be ingested, but do not write outputs and do not
  update checkpoint.
- If dry_run=false:
  - Perform the ingest and update the checkpoint on success.

2. Local lake output (JSONL): Write JSONL output for each table to the local filesystem.
Required layout:
- ./lake/customers/date=YYYY-MM-DD/data.jsonl
- ./lake/cases/date=YYYY-MM-DD/data.jsonl

Rules:
- Output should be valid JSONL (1 JSON object per line).
- Re-running ingest with no DB changes must not create duplicates (overwrite is acceptable).
- Keep it simple; correctness > fancy partitioning.

3. Manifest (returned by the API): Each ingest run must return a JSON manifest in the response body
Include at least:
- run_id
- started_at, finished_at
- For each table:
  - row count ingested in this run
  - lake output paths written
- checkpoint_before, checkpoint_after
- schema_fingerprint per table (hash of column names/types is enough)

4. Delta events (one per table): After a successful ingest, emit one event per table.
 - Emit as JSON to:
  - stdout
  - append to ./events/events.jsonl
Event fields (minimum):
- table
- run_id
- schema_fingerprint
- delta_row_count
- lake_paths
- checkpoint_after

5. AI-ready deterministic search (cases): Expose a similarity search endpoint over cases.
Endpoint
POST /search
Request body:
`{ "query": "text", "top_k": 5 }`
Required behavior:
- Create a deterministic “embedding-like” representation (hash-based is fine).
- Maintain an in-memory index of cases that supports top-k similarity.
- The index must reflect ingested data (e.g., updated on /ingest, or built from the lake on startup).
- Return results with:
  - case_id
  - score
  - (recommended) title, status

## Tests (minimum)
Provide at least two automated tests:
1. Checkpoint correctness
   a. checkpoint advances only on success
   b. idempotent rerun does not duplicate outputs
2. Search determinism
   a. same query + same data ⇒ same ordered top_k results

## Documentation (required)
README.md
- How to run (expected commands)
- How to call endpoints (example curl is fine)
- Key assumptions and tradeoffs

### AI_USAGE.md (required)
We want to understand how you used agentic coding.
Include:
- Which tools/agents you used
- The most important prompts (or transcript excerpts)
- What you verified manually (commands, tests, edge cases)
- Any mistakes the agent made and how you corrected them

## ARCHITECTURE_AWS.md (required, max 1 page)
Describe how you would run this on AWS in production. Include:
- A high-level diagram (ASCII is fine)
- Service choices for:
  - Postgres (RDS/Aurora)
  - Compute (ECS/Fargate or Lambda)
  - Data lake (S3) + catalog/query (Glue/Athena or equivalent)
  - Checkpoint/state store (DynamoDB or equivalent)
  - Eventing (EventBridge/SNS/SQS + DLQ)
  - Vector search + embedding generation (e.g., OpenSearch + Bedrock/SageMaker)
- Idempotency strategy and replay safety
- Failure handling (retries, DLQs)
- Security/ops basics (IAM, secrets, encryption, observability)

## Stretch goals (optional)
Only if you have time left:
- Real S3/MinIO output
- Real queue integration (SQS/Redis Streams)
- Stronger schema evolution handling (explicit versions, compatibility)

## How we evaluate
We’re looking for senior-level thinking and execution:
- Correct incremental ingest + safe checkpointing
- Clean boundaries and maintainable structure
- Failure handling and idempotency
- Deterministic, testable search behavior
- Tests that validate real behavior
- Clear docs (especially AI usage and AWS architecture)

## Submission
- Provide a repo link or zip.
- We should be able to run:
  - `docker compose up`
  - Your service
- And call `/ingest` and `/search` successfully.
