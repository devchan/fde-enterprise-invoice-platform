# -----------------------------------------------------------------------------
# Invoice platform infrastructure skeleton.
#
# Scope: this module provisions the *container-platform prerequisites* for the
# invoice platform. The Kubernetes workloads themselves are defined as kustomize
# overlays under ../k8s and are expected to be applied by CI (kubectl apply -k)
# or a GitOps controller (Argo CD / Flux). This skeleton is intentionally
# cloud-neutral: swap the commented stubs below for concrete resources from your
# provider of choice (AWS RDS/ElastiCache/S3, GCP Cloud SQL/Memorystore/GCS,
# Azure, etc.).
# -----------------------------------------------------------------------------

locals {
  common_tags = {
    "app.kubernetes.io/part-of" = "invoice-platform"
    environment                 = var.environment
  }
}

# The kubernetes provider is configured from the caller's current context by
# default. In real use, wire this to the cluster provisioned by your cloud
# module (endpoint + token/cert). Left context-based so `validate` passes.
provider "kubernetes" {}

provider "null" {}

# --- Concrete, validatable resource -----------------------------------------
# Namespace the platform runs in. This is a real resource that `terraform
# validate` accepts and that a real apply would create in-cluster.
resource "kubernetes_namespace_v1" "platform" {
  metadata {
    name   = var.namespace
    labels = local.common_tags
  }
}

# --- Kustomize apply hook -----------------------------------------------------
# Applies the environment overlay after the namespace exists. Replace with a
# proper CI/GitOps step in production; this null_resource documents the wiring
# and keeps the graph concrete for validation.
resource "null_resource" "apply_kustomize_overlay" {
  triggers = {
    environment        = var.environment
    backend_image_tag  = var.backend_image_tag
    frontend_image_tag = var.frontend_image_tag
    namespace          = kubernetes_namespace_v1.platform.metadata[0].name
  }

  # provisioner "local-exec" {
  #   command = "kubectl apply -k ${path.module}/../k8s/overlays/${var.environment}"
  # }
}

# --- Managed data services (stubs) -------------------------------------------
# Postgres and Redis are treated as EXTERNAL managed services. Provision them
# with your cloud provider and feed their connection strings into the platform
# Secret via var.db_url / var.redis_url. Example placeholders:
#
# resource "aws_db_instance" "postgres" {
#   identifier     = "invoice-platform-${var.environment}"
#   engine         = "postgres"
#   engine_version = "16"
#   instance_class = "db.t3.medium"
#   # ...
# }
#
# resource "aws_elasticache_cluster" "redis" {
#   cluster_id = "invoice-platform-${var.environment}"
#   engine     = "redis"
#   # ...
# }
#
# resource "aws_s3_bucket" "invoices" {
#   bucket = var.object_storage_bucket
# }

# --- Platform Secret ----------------------------------------------------------
# Materialize the sensitive connection strings into the in-cluster Secret the
# backend/worker consume. In production prefer External Secrets Operator or
# Sealed Secrets over writing secrets through Terraform state.
resource "kubernetes_secret_v1" "platform" {
  metadata {
    name      = "invoice-platform-secrets"
    namespace = kubernetes_namespace_v1.platform.metadata[0].name
    labels    = local.common_tags
  }

  type = "Opaque"

  data = {
    DATABASE_URL = var.db_url
    REDIS_URL    = var.redis_url
    JWT_SECRET   = var.jwt_secret
  }
}
