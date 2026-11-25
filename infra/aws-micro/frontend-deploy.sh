#!/usr/bin/env bash
# =============================================================================
# Build the SPA and host it on S3 + CloudFront — the near-free frontend tier.
# Run this from your laptop/CI (needs: aws cli v2, node/npm, jq).
#
# Why S3 + CloudFront instead of a container: the built bundle is static files,
# so serving it from object storage costs pennies and frees RAM on the tiny box.
#
# The API base URL is BAKED INTO the bundle at build time, so this script must
# know your backend's public address (the EC2 public DNS / your API domain).
#
# Usage:
#   API_BASE_URL=http://<ec2-public-dns>:8000 \
#   BUCKET=my-invoice-frontend \
#   ./frontend-deploy.sh
# =============================================================================
set -euo pipefail

: "${API_BASE_URL:?set API_BASE_URL to your backend's public URL (baked into the build)}"
: "${BUCKET:?set BUCKET to a globally-unique S3 bucket name}"
REGION="${REGION:-us-east-1}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo ">> Building frontend with VITE_API_BASE_URL=${API_BASE_URL}"
cd "${REPO_ROOT}/frontend"
npm ci
VITE_API_BASE_URL="${API_BASE_URL}" npm run build   # outputs to frontend/dist

echo ">> Ensuring S3 bucket s3://${BUCKET} exists"
if ! aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
  if [ "${REGION}" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}"
  else
    aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}" \
      --create-bucket-configuration LocationConstraint="${REGION}"
  fi
fi

echo ">> Uploading bundle"
# Hashed assets are immutable -> cache forever; index.html must never cache so
# new deploys are picked up immediately (mirrors the nginx.conf caching rules).
aws s3 sync dist/ "s3://${BUCKET}/" --delete \
  --exclude index.html --cache-control "public,max-age=31536000,immutable"
aws s3 cp dist/index.html "s3://${BUCKET}/index.html" \
  --cache-control "no-cache"

echo
echo ">> Bundle uploaded. To finish the CloudFront setup (one-time):"
cat <<'EOF'
  1. Create a CloudFront distribution with this S3 bucket as the origin,
     using an Origin Access Control (OAC) so the bucket stays private:
       aws cloudfront create-distribution \
         --origin-domain-name <BUCKET>.s3.<REGION>.amazonaws.com \
         --default-root-object index.html
  2. Add an SPA error mapping: 403 and 404 -> /index.html (200), so client-side
     routing works (same role as nginx `try_files ... /index.html`).
  3. Copy the distribution's *.cloudfront.net domain, then:
       - set CORS_ALLOWED_ORIGINS on the backend to https://<domain>
       - rerun this script with API_BASE_URL pointing at your backend if it changed
  4. Redeploy the bundle later with just this script, then invalidate the cache:
       aws cloudfront create-invalidation --distribution-id <ID> --paths "/index.html"
EOF
