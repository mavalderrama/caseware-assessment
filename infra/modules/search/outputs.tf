output "collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint"
  value       = aws_opensearchserverless_collection.main.collection_endpoint
}

output "collection_arn" {
  value = aws_opensearchserverless_collection.main.arn
}
