data "aws_caller_identity" "current" {}

# ── S3 Data Lake ──────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "lake" {
  bucket = "${var.name_prefix}-data-lake-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${var.name_prefix}-data-lake" }
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter { prefix = "" }

    transition {
      days          = var.lake_lifecycle_ia_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.lake_lifecycle_glacier_days
      storage_class = "GLACIER"
    }
  }
}

# ── DynamoDB Checkpoint Table ─────────────────────────────────────────────────

resource "aws_dynamodb_table" "checkpoints" {
  name         = "${var.name_prefix}-checkpoints"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "table_name"

  attribute {
    name = "table_name"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = { Name = "${var.name_prefix}-checkpoints" }
}
