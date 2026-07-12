# Terraform — invoice platform infrastructure skeleton

A cloud-neutral skeleton that provisions the **container-platform prerequisites**
for the invoice platform. It is deliberately minimal and meant to be extended
with concrete resources for your target cloud.

## What this models

- A Kubernetes `Namespace` for the platform (concrete, appliable resource).
- The in-cluster `Secret` holding the sensitive connection strings
  (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`).
- A hook (`null_resource`) documenting how the kustomize overlay under
  `../k8s/overlays/<environment>` is applied after the namespace exists.
- Commented stubs for the **external managed services** (Postgres, Redis,
  object storage). Postgres and Redis are intentionally NOT run in-cluster;
  provision them with your cloud provider and pass their URLs via variables.

## Files

| File | Purpose |
| --- | --- |
| `versions.tf` | `required_version`, `required_providers`, remote-backend note |
| `variables.tf` | Inputs: region, environment, image tags, sensitive URLs/secret |
| `main.tf` | Providers + concrete resources + managed-service stubs |
| `outputs.tf` | Namespace, environment, image tag, secret name |

## Usage

```bash
# Validation (no cloud credentials needed):
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate

# Real use — configure a remote backend first (see versions.tf), then:
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform apply \
  -var 'environment=staging' \
  -var 'namespace=invoice-platform-staging' \
  -var 'db_url=...' -var 'redis_url=...' -var 'jwt_secret=...'
```

## Notes

- **Remote state is required** for real environments. `versions.tf` documents an
  example S3 + DynamoDB locking backend; it is left unconfigured so
  `init -backend=false` works for validation.
- **Secrets**: `db_url`, `redis_url`, and `jwt_secret` are marked
  `sensitive = true`. Writing secrets through Terraform state is convenient but
  puts them in state — prefer the External Secrets Operator or Sealed Secrets
  (see `../k8s/base/secret.example.yaml`) for production.
- The `kubernetes` provider uses the caller's current kube-context by default;
  wire it to the cluster your cloud module provisions before applying.
