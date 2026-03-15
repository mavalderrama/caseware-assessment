data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── OpenSearch Serverless Encryption Policy ───────────────────────────────────

resource "aws_opensearchserverless_security_policy" "encryption" {
  name        = "${var.name_prefix}-enc"
  type        = "encryption"
  description = "Encryption policy for ${var.name_prefix} collection"

  policy = jsonencode({
    Rules = [{
      ResourceType = "collection"
      Resource     = ["collection/${var.name_prefix}-search"]
    }]
    AWSOwnedKey = true
  })
}

# ── OpenSearch Serverless Network Policy ──────────────────────────────────────

resource "aws_opensearchserverless_security_policy" "network" {
  name        = "${var.name_prefix}-net"
  type        = "network"
  description = "Network policy for ${var.name_prefix} collection"

  policy = jsonencode([{
    Rules = [{
      ResourceType = "collection"
      Resource     = ["collection/${var.name_prefix}-search"]
    }, {
      ResourceType = "dashboard"
      Resource     = ["collection/${var.name_prefix}-search"]
    }]
    AllowFromPublic = false
    SourceVPCEs     = [aws_opensearchserverless_vpc_endpoint.main.id]
  }])
}

# ── OpenSearch Serverless VPC Endpoint ───────────────────────────────────────

resource "aws_opensearchserverless_vpc_endpoint" "main" {
  name               = "${var.name_prefix}-opensearch-vpce"
  vpc_id             = var.vpc_id
  subnet_ids         = var.subnet_ids
  security_group_ids = [var.security_group_id]
}

# ── OpenSearch Serverless Data Access Policy ──────────────────────────────────

resource "aws_opensearchserverless_access_policy" "main" {
  name        = "${var.name_prefix}-access"
  type        = "data"
  description = "Data access policy for ${var.name_prefix}"

  policy = jsonencode([{
    Rules = [{
      ResourceType = "index"
      Resource     = ["index/${var.name_prefix}-search/*"]
      Permission = [
        "aoss:CreateIndex",
        "aoss:DeleteIndex",
        "aoss:UpdateIndex",
        "aoss:DescribeIndex",
        "aoss:ReadDocument",
        "aoss:WriteDocument"
      ]
    }, {
      ResourceType = "collection"
      Resource     = ["collection/${var.name_prefix}-search"]
      Permission = [
        "aoss:CreateCollectionItems",
        "aoss:DeleteCollectionItems",
        "aoss:UpdateCollectionItems",
        "aoss:DescribeCollectionItems"
      ]
    }]
    Principal = [var.task_role_arn]
  }])
}

# ── OpenSearch Serverless Collection ─────────────────────────────────────────

resource "aws_opensearchserverless_collection" "main" {
  name        = "${var.name_prefix}-search"
  type        = "VECTORSEARCH"
  description = "Vector search collection for ${var.name_prefix} cases"

  tags = { Name = "${var.name_prefix}-search" }

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}
