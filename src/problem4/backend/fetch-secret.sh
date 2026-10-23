#!/usr/bin/env bash
set -euo pipefail
umask 077
region="$(jq -er '.region' /etc/shipit/backend-host.json)"
secret_arn="$(jq -er '.secret_arn' /etc/shipit/backend-host.json)"
secret_tmp="$(mktemp /run/shipit-backend/.secret.XXXXXX)"
trap 'rm -f "$secret_tmp"' EXIT
aws secretsmanager get-secret-value --region "$region" --secret-id "$secret_arn" \
  --query SecretString --output text --cli-connect-timeout 5 --cli-read-timeout 15 > "$secret_tmp"
jq -e 'type == "object"' "$secret_tmp" >/dev/null
install -o root -g shipit-backend -m 0440 "$secret_tmp" /run/shipit-backend/runtime.json
