variable "region" {
  description = "Cloud region for managed resources (Postgres, Redis, object storage)."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name (e.g. staging, production)."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be one of: staging, production."
  }
}

variable "namespace" {
  description = "Kubernetes namespace to create for the platform."
  type        = string
  default     = "invoice-platform-staging"
}

variable "backend_image_tag" {
  description = "Container image tag for the backend/worker image."
  type        = string
  default     = "staging"
}

variable "frontend_image_tag" {
  description = "Container image tag for the frontend image."
  type        = string
  default     = "staging"
}

variable "db_url" {
  description = "Full SQLAlchemy DATABASE_URL for the managed Postgres instance."
  type        = string
  sensitive   = true
}

variable "redis_url" {
  description = "REDIS_URL for the managed Redis instance."
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "JWT signing secret for the backend."
  type        = string
  sensitive   = true
}

variable "object_storage_bucket" {
  description = "Object storage bucket name for uploaded invoices."
  type        = string
  default     = "invoice-platform-staging"
}
