#!/usr/bin/env sh
set -eu

APP_URL="${APP_URL:-http://localhost:3000/}"
BROWSER="${BROWSER:-google-chrome}"
RUN_ID="$(date +%s)"
OUTPUT_FILE="/tmp/fde-cockpit-smoke-${RUN_ID}.html"
USER_DATA_DIR="/tmp/fde-cockpit-smoke-profile-${RUN_ID}"

if ! command -v "$BROWSER" >/dev/null 2>&1; then
  echo "Browser executable not found: $BROWSER" >&2
  exit 127
fi

"$BROWSER" \
  --headless=new \
  --disable-gpu \
  --no-sandbox \
  --user-data-dir="$USER_DATA_DIR" \
  --dump-dom "$APP_URL" > "$OUTPUT_FILE"

grep -q 'Reviewer Cockpit' "$OUTPUT_FILE"
grep -q 'Upload' "$OUTPUT_FILE"
grep -q 'Review Queue' "$OUTPUT_FILE"
grep -q 'Failed Jobs' "$OUTPUT_FILE"
grep -q 'Audit Logs' "$OUTPUT_FILE"
grep -q 'React frontend' "$OUTPUT_FILE"

echo "Cockpit browser smoke passed for $APP_URL"
