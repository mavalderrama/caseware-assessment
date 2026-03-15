output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.compute.alb_dns_name
}

output "db_cluster_endpoint" {
  description = "Aurora cluster writer endpoint"
  value       = module.database.cluster_endpoint
  sensitive   = true
}

output "db_secret_arn" {
  description = "ARN of the Secrets Manager secret holding DB credentials"
  value       = module.database.secret_arn
  sensitive   = true
}

output "lake_bucket_name" {
  description = "S3 bucket name for the data lake"
  value       = module.storage.lake_bucket_name
}

output "checkpoint_table_name" {
  description = "DynamoDB table name for checkpoints"
  value       = module.storage.checkpoint_table_name
}

output "events_queue_url" {
  description = "SQS queue URL for delta events"
  value       = module.eventing.queue_url
}

output "events_dlq_url" {
  description = "SQS dead-letter queue URL"
  value       = module.eventing.dlq_url
}

output "opensearch_endpoint" {
  description = "OpenSearch Serverless collection endpoint"
  value       = module.search.collection_endpoint
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.compute.cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = module.compute.service_name
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}
