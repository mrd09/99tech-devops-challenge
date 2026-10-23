#!/usr/bin/env bash
set -euo pipefail
expected="$(jq -er '.commit' /opt/shipit/backend/current/release.json)"
for attempt in {1..10}; do
  if systemctl is-active --quiet shipit-backend.service &&
     curl --fail --silent --show-error --max-time 2 http://127.0.0.1:3000/health/ready >/dev/null &&
     curl --fail --silent --show-error --max-time 2 http://127.0.0.1:3000/version |
       jq -e --arg sha "$expected" '.commit == $sha' >/dev/null; then
    exit 0
  fi
  sleep 2
done
echo 'Local readiness/release identity check failed' >&2
exit 1
