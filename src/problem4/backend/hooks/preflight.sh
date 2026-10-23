#!/usr/bin/env bash
set -euo pipefail
for tool in /usr/bin/node aws curl jq python3 systemctl; do
  command -v "$tool" >/dev/null
done
id shipit-backend >/dev/null
test -r /etc/shipit/backend-host.json
test "$(uname -m)" = x86_64
python3 - <<'PY'
import json, pathlib, subprocess
os_release = dict(line.split('=', 1) for line in pathlib.Path('/etc/os-release').read_text().splitlines() if '=' in line)
if os_release.get('ID', '').strip('"') != 'ubuntu' or os_release.get('VERSION_ID', '').strip('"') != '24.04':
    raise SystemExit('Expected Ubuntu 24.04')
if subprocess.check_output(['/usr/bin/node', '-p', 'process.versions.node.split(".")[0]'], text=True).strip() != '24':
    raise SystemExit('Expected Node 24')
host = json.loads(pathlib.Path('/etc/shipit/backend-host.json').read_text())
if not host.get('region') or not host.get('secret_arn'):
    raise SystemExit('Missing host region/secret ARN')
PY
