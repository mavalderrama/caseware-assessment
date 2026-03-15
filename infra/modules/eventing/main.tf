# ── KMS Key for SQS encryption ────────────────────────────────────────────────

resource "aws_kms_key" "sqs" {
  description             = "KMS key for ${var.name_prefix} SQS queues"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = { Name = "${var.name_prefix}-sqs-kms" }
}

resource "aws_kms_alias" "sqs" {
  name          = "alias/${var.name_prefix}-sqs"
  target_key_id = aws_kms_key.sqs.key_id
}

# ── Dead Letter Queue ─────────────────────────────────────────────────────────

resource "aws_sqs_queue" "events_dlq" {
  name                      = "${var.name_prefix}-events-dlq"
  message_retention_seconds = var.message_retention_seconds
  kms_master_key_id         = aws_kms_key.sqs.id
  tags                      = { Name = "${var.name_prefix}-events-dlq" }
}

# ── Main Events Queue ─────────────────────────────────────────────────────────

resource "aws_sqs_queue" "events" {
  name                       = "${var.name_prefix}-events"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  kms_master_key_id          = aws_kms_key.sqs.id

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.events_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = { Name = "${var.name_prefix}-events" }
}

resource "aws_sqs_queue_policy" "events" {
  queue_url = aws_sqs_queue.events.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridge"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.events.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_cloudwatch_event_rule.delta_events.arn
        }
      }
    }]
  })
}

# ── EventBridge Custom Bus ────────────────────────────────────────────────────

resource "aws_cloudwatch_event_bus" "main" {
  name = var.name_prefix
  tags = { Name = "${var.name_prefix}-event-bus" }
}

resource "aws_cloudwatch_event_rule" "delta_events" {
  name           = "${var.name_prefix}-delta-events"
  description    = "Capture all delta events from ${var.name_prefix}"
  event_bus_name = aws_cloudwatch_event_bus.main.name

  event_pattern = jsonencode({
    source = ["datasearchpy.ingest"]
  })

  tags = { Name = "${var.name_prefix}-delta-events-rule" }
}

resource "aws_cloudwatch_event_target" "sqs" {
  rule           = aws_cloudwatch_event_rule.delta_events.name
  event_bus_name = aws_cloudwatch_event_bus.main.name
  target_id      = "SendToSQS"
  arn            = aws_sqs_queue.events.arn

  dead_letter_config {
    arn = aws_sqs_queue.events_dlq.arn
  }

  retry_policy {
    maximum_retry_attempts       = 3
    maximum_event_age_in_seconds = 3600
  }
}
