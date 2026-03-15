output "lake_bucket_name" {
  value = aws_s3_bucket.lake.bucket
}

output "lake_bucket_arn" {
  value = aws_s3_bucket.lake.arn
}

output "checkpoint_table_name" {
  value = aws_dynamodb_table.checkpoints.name
}

output "checkpoint_table_arn" {
  value = aws_dynamodb_table.checkpoints.arn
}
