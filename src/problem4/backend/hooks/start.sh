#!/usr/bin/env bash
set -euo pipefail
release_id="$(jq -er '.release_id' /opt/shipit/backend/incoming/release.json)"
[[ "$release_id" =~ ^[0-9a-f]{40}-[0-9]+-[0-9]+$ ]]
release_path="/opt/shipit/backend/releases/$release_id"
test -f "$release_path/dist/server.js"
ln -sfn "$release_path" /opt/shipit/backend/current.next
mv -Tf /opt/shipit/backend/current.next /opt/shipit/backend/current
systemctl enable shipit-backend.service
systemctl restart shipit-backend.service
