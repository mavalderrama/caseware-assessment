# AWS Production Architecture

## High-level diagram

```
                    ┌─────────────────────────────────────────────────────────┐
                    │  VPC (private subnets)                                  │
                    │                                                         │
  Internet ──► ALB ──► ECS Fargate (Django) ──► Aurora PostgreSQL Serverless │
                    │        │                   (pgvector extension)         │
                    │        │ writes                                         │
                    │        ▼                                                │
                    │   S3 Data Lake                                          │
                    │   lake/{table}/date=YYYY-MM-DD/data.jsonl               │
                    │        │                                                │
                    │        │ trigger / catalog                              │
                    │        ▼                                                │
                    │   AWS Glue (crawler) ──► Glue Data Catalog              │
                    │                              │                          │
                    │                              ▼                          │
                    │                         Amazon Athena (ad-hoc SQL)      │
                    │                                                         │
                    │        │ delta events                                   │
                    │        ▼                                                │
                    │   EventBridge (custom bus) ──► SQS + DLQ               │
                    │                                                         │
                    │        │ checkpoint                                     │
                    │        ▼                                                │
                    │   DynamoDB (checkpoint table)                           │
                    │        key: table_name  value: updated_at cursor        │
                    │                                                         │
                    │        │ embeddings                                     │
                    │        ▼                                                │
                    │   OpenSearch Serverless (vector search)                 │
                    │   ← Bedrock / SageMaker (embedding generation)          │
                    └─────────────────────────────────────────────────────────┘
```

## Service choices

| Concern | Service | Reason |
|---|---|---|
| **Postgres** | Aurora PostgreSQL Serverless v2 | Auto-scales to zero when idle; supports pgvector; IAM auth; cluster endpoint for HA |
| **Compute** | ECS Fargate | No server management; per-request scaling; integrates with ALB and Secrets Manager |
| **Data lake** | S3 + Glue crawler + Athena | S3 for durable JSONL storage; Glue auto-catalogs partitions; Athena for ad-hoc SQL without ETL |
| **Checkpoint / state** | DynamoDB | Single-item conditional writes for atomic checkpoint advancement; PAY_PER_REQUEST; global tables for multi-region |
| **Eventing** | EventBridge → SQS + DLQ | EventBridge for routing/filtering; SQS for reliable delivery; DLQ captures unprocessable messages for replay |
| **Vector search** | OpenSearch Serverless (k-NN) | Managed, no cluster ops; natively supports 384-dim vectors; scales with query volume |
| **Embeddings** | Amazon Bedrock (Titan Embeddings) or SageMaker endpoint | Managed inference; no model serving infrastructure; Bedrock requires no provisioning |

## Idempotency strategy

- **Ingest**: checkpoint is a strict `updated_at__gt` cursor stored atomically in DynamoDB via conditional write (`attribute_not_exists` or version check). Re-running produces the same S3 object keys (same day partition → same path); S3 PUT is idempotent.
- **Events**: each event carries a `run_id`; consumers deduplicate by `run_id` + `table` using a DynamoDB idempotency table or SQS message deduplication ID (FIFO queue).
- **Search index rebuild**: re-reading all S3 partitions and re-indexing into OpenSearch with `_id = case_id` is idempotent (upsert).

## Failure handling

- **ECS task crash during lake write**: S3 multipart uploads with abort-on-failure; checkpoint is only written to DynamoDB *after* all S3 puts succeed.
- **SQS consumer failure**: messages stay in queue up to visibility timeout; after `maxReceiveCount` retries they move to the DLQ for manual inspection / replay.
- **OpenSearch indexing failure**: logged to CloudWatch; a separate reconciliation job can re-index from S3 on demand.
- **Aurora failover**: Aurora Serverless v2 promotes a reader within ~30 s; ECS task retries DB connection with exponential back-off.

## Security / ops basics

- **IAM**: task role grants least-privilege (S3 prefix, specific DynamoDB table, SQS queue ARN only). No wildcard `*` resources.
- **Secrets**: DB credentials injected via Secrets Manager; never in environment variables or source code.
- **Encryption**: S3 SSE-S3 (or SSE-KMS for stricter compliance); DynamoDB encryption at rest; SQS KMS; RDS storage encrypted; OpenSearch encryption policy.
- **Network**: ECS tasks in private subnets; ALB in public subnets; RDS and OpenSearch only reachable from ECS security group.
- **Observability**: CloudWatch Logs (ECS), CloudWatch Metrics + alarms (CPU, ALB 5xx, DLQ depth), X-Ray tracing for request latency.
- **Audit**: CloudTrail for all API calls; S3 access logging; DynamoDB streams for checkpoint history.
