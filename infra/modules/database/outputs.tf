output "cluster_endpoint" {
  description = "Aurora cluster writer endpoint"
  value       = aws_rds_cluster.main.endpoint
}

output "cluster_reader_endpoint" {
  description = "Aurora cluster reader endpoint"
  value       = aws_rds_cluster.main.reader_endpoint
}

output "cluster_id" {
  value = aws_rds_cluster.main.cluster_identifier
}

output "secret_arn" {
  description = "Secrets Manager secret ARN containing DB credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}
