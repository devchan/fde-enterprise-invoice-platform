output "namespace" {
  description = "Kubernetes namespace created for the platform."
  value       = kubernetes_namespace_v1.platform.metadata[0].name
}

output "environment" {
  description = "Environment this state manages."
  value       = var.environment
}

output "region" {
  description = "Cloud region for managed resources."
  value       = var.region
}

output "backend_image_tag" {
  description = "Backend/worker image tag deployed by this state."
  value       = var.backend_image_tag
}

output "secret_name" {
  description = "Name of the in-cluster Secret holding connection strings."
  value       = kubernetes_secret_v1.platform.metadata[0].name
  sensitive   = true
}
