#!/usr/bin/env bash
# LocalStack init script — runs once LocalStack is ready.
# Creates the SQS queues and S3 lake bucket used by the app.
set -euo pipefail

REGION="us-east-1"
ENDPOINT="http://localhost:4566"

echo "[localstack-init] Creating SQS queues..."

# Dead-letter queue first so the main queue can reference it
awslocal --region "$REGION" sqs create-queue \
  --queue-name datasearchpy-events-dlq \
  --attributes '{
    "MessageRetentionPeriod": "1209600"
  }'

DLQ_ARN=$(awslocal --region "$REGION" sqs get-queue-attributes \
  --queue-url "${ENDPOINT}/000000000000/datasearchpy-events-dlq" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)

echo "[localstack-init] DLQ ARN: ${DLQ_ARN}"

# Main events queue with redrive policy pointing to DLQ
awslocal --region "$REGION" sqs create-queue \
  --queue-name datasearchpy-events \
  --attributes "{
    \"VisibilityTimeout\": \"300\",
    \"MessageRetentionPeriod\": \"1209600\",
    \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
  }"

echo "[localstack-init] Creating S3 lake bucket..."

awslocal --region "$REGION" s3 mb s3://datasearchpy-lake

# Enable versioning on the lake bucket
awslocal --region "$REGION" s3api put-bucket-versioning \
  --bucket datasearchpy-lake \
  --versioning-configuration Status=Enabled

echo "[localstack-init] Done. Resources created:"
echo "  SQS: datasearchpy-events"
echo "  SQS: datasearchpy-events-dlq"
echo "  S3:  datasearchpy-lake"
