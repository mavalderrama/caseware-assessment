# AWS Production Architecture

## High-level diagram

```
                         ┌─────────────────────────────────────────────────────────────┐
                         │  VPC                                                        │
                         │                                                             │
                         │  Public subnets                                             │
  Internet ──► Route53   │  ┌──────────────────────────────────────┐                  │
               (optional)│  │  ALB (HTTP :80 / HTTPS :443)         │                  │
                    │    │  └──────────────┬───────────────────────┘                  │
                    │    │                 │ port 8000                                 │
                    │    │  Private subnets│                                           │
                    │    │  ┌──────────────▼──────────────────────────────────────┐   │
                    │    │  │  ECS Fargate (Django, FARGATE + FARGATE_SPOT)        │   │
                    │    │  │  Auto-scales on CPU (target 70%)                     │   │
                    │    │  │  Deployment circuit-breaker + rollback               │   │
                    │    │  └──────┬──────────┬──────────┬──────────┬─────────────┘   │
                    │    │         │           │          │          │                  │
                    │    │  reads  │    writes │  writes  │ publishes│                  │
                    │    │         ▼           ▼          ▼          ▼                  │
                    │    │  ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐   │
                    │    │  │  Aurora  │ │  S3     │ │ DynamoDB │ │ EventBridge  │   │
                    │    │  │ Postgres │ │ Data    │ │Checkpoint│ │ Custom Bus   │   │
                    │    │  │Serverless│ │  Lake   │ │  Table   │ │(source:      │   │
                    │    │  │   v2     │ │ (JSONL  │ │ (atomic  │ │datasearchpy  │   │
                    │    │  │          │ │partition│ │ cursor)  │ │  .ingest)    │   │
                    │    │  └──────────┘ │ed by    │ └──────────┘ └──────┬───────┘   │
                    │    │               │ date)   │                      │            │
                    │    │               └─────────┘           ┌──────────▼────────┐  │
                    │    │                                      │  SQS + DLQ        │  │
                    │    │                                      │  (KMS-encrypted,  │  │
                    │    │                                      │  3 retries, 1h)   │  │
                    │    │                                      └───────────────────┘  │
                    │    │                                                             │
                    │    │  ┌──────────────────────────────────────────────────────┐  │
                    │    │  │  OpenSearch Serverless (VECTORSEARCH collection)      │  │
                    │    │  │  VPC endpoint — reachable only from ECS SG           │  │
                    │    │  └──────────────────────────────────────────────────────┘  │
                    │    └─────────────────────────────────────────────────────────────┘
```

## Service choices

| Concern | Service | Reason |
|---|---|---|
| **Postgres (source)** | Aurora PostgreSQL Serverless v2 | Scales 0.5–16 ACU; storage encrypted; enhanced monitoring + Performance Insights; credentials in Secrets Manager |
| **Compute** | ECS Fargate + FARGATE_SPOT | No server management; SPOT reduces cost; ALB integration; CPU auto-scaling; deployment circuit-breaker with rollback |
| **Data lake** | S3 (SSE-S3, versioning, lifecycle IA→Glacier) | Durable JSONL storage; same-day partition key makes PUTs idempotent; lifecycle tiers reduce cost over time |
| **Checkpoint / state** | DynamoDB (PAY_PER_REQUEST, PITR, encrypted) | Single-item conditional writes for atomic checkpoint advancement; point-in-time recovery for audit |
| **Eventing** | EventBridge custom bus → SQS + DLQ (KMS) | EventBridge filters on `source: datasearchpy.ingest`; SQS gives durable buffering; DLQ captures after 3 retries |
| **Vector search** | OpenSearch Serverless (VECTORSEARCH, VPC endpoint) | Managed, no cluster ops; scales with query volume; VPC endpoint keeps traffic private; task-role data-access policy |
| **Embeddings** | Amazon Bedrock (Titan Embeddings v2) or SageMaker | Managed inference for production; current implementation uses hash-based scoring — swap embedding function only |

## Idempotency strategy

- **Ingest**: checkpoint is an `updated_at__gt` cursor stored atomically in DynamoDB. Re-running with no DB changes writes to the same S3 key (`lake/{table}/date=YYYY-MM-DD/data.jsonl`) — S3 PUT is idempotent. Dry-run mode (`?dry_run=true`) skips all writes.
- **Events**: each event carries a `run_id`; EventBridge source filter (`datasearchpy.ingest`) prevents spurious routing; SQS consumers deduplicate by `run_id + table`.
- **Search index rebuild**: re-indexing from S3 into OpenSearch using `_id = case_id` is an idempotent upsert.

## Failure handling

- **ECS task crash during lake write**: checkpoint advances only *after* all S3 PUTs succeed; partial writes are overwritten on retry.
- **SQS consumer failure**: messages remain in-flight up to the visibility timeout; after 3 receive attempts they move to the DLQ for inspection / manual replay. EventBridge also retries delivery for up to 1 hour.
- **OpenSearch indexing failure**: logged to CloudWatch; a reconciliation run re-indexes from S3 on demand (`_id`-keyed upserts are safe to replay).
- **Aurora failover**: Serverless v2 promotes a reader in ~30 s; ECS task retries with exponential back-off.
- **ECS bad deploy**: deployment circuit-breaker detects unhealthy task startup and auto-rolls back to the previous task definition.

## Security / ops basics

- **IAM**: task role grants least-privilege — specific S3 prefix, DynamoDB table ARN, SQS queue ARN, EventBridge bus ARN only; no wildcard `*` resources.
- **Secrets**: DB credentials stored in Secrets Manager; injected at runtime via `secrets` block in task definition — never in env vars or source code.
- **Encryption**: S3 SSE-S3; DynamoDB encryption at rest; SQS + DLQ with dedicated KMS key (auto-rotated); Aurora storage encrypted; OpenSearch AWS-owned key encryption policy.
- **Network**: ECS tasks in private subnets (NAT for egress); ALB in public subnets; Aurora port 5432 reachable only from ECS SG; OpenSearch VPCE reachable only from ECS SG.
- **Observability**: CloudWatch Logs (ECS, 30-day retention); CloudWatch alarms on ECS CPU > 80% and ALB 5xx count > 10; Aurora enhanced monitoring (60 s) + Performance Insights (7-day); DynamoDB PITR for checkpoint audit trail.