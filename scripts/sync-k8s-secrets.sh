#!/usr/bin/env bash
set -euo pipefail
set +x

for name in \
  RDS_ENDPOINT DB_PORT OS_DATABASE OS_DATABASE_USERNAME OS_DB_PASSWORD \
  NEW_RELIC_LICENSE_KEY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required deployment configuration: %s\n' "$name" >&2
    exit 2
  fi
done

database_url="$(python3 <<'PY'
import os
from urllib.parse import quote

username = quote(os.environ["OS_DATABASE_USERNAME"], safe="")
password = quote(os.environ["OS_DB_PASSWORD"], safe="")
host = os.environ["RDS_ENDPOINT"]
port = os.environ["DB_PORT"]
database = quote(os.environ["OS_DATABASE"], safe="")
print(f"postgresql+psycopg://{username}:{password}@{host}:{port}/{database}")
PY
)"

kubectl --namespace oficina create secret generic os-service-secrets \
  --from-literal="DATABASE_URL=${database_url}" \
  --from-literal="NEW_RELIC_LICENSE_KEY=${NEW_RELIC_LICENSE_KEY}" \
  --from-literal="AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}" \
  --from-literal="AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}" \
  --from-literal="AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

printf 'OS Service Kubernetes Secret synchronized\n'
