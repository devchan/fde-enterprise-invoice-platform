terraform {
  required_version = ">= 1.5.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.23.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2.0"
    }
  }

  # Backend state MUST be remote and locked in real environments. Configure it
  # per-environment (do not commit real bucket/table names), e.g.:
  #
  #   backend "s3" {
  #     bucket         = "invoice-platform-tfstate"
  #     key            = "invoice-platform/<env>/terraform.tfstate"
  #     region         = "us-east-1"
  #     dynamodb_table = "invoice-platform-tflock"
  #     encrypt        = true
  #   }
  #
  # Left unconfigured here so `terraform init -backend=false` works for
  # validation. Enable one of the remote backends above before real applies.
}
