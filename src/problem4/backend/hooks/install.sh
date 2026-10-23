#!/usr/bin/env bash
set -euo pipefail
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$source_root" <<'PY'
import json, pathlib, re, shutil, subprocess, sys
source = pathlib.Path(sys.argv[1])
incoming = pathlib.Path('/opt/shipit/backend/incoming')
metadata = json.loads((incoming / 'release.json').read_text())
release = metadata['release_id']
if not re.fullmatch(r'[0-9a-f]{40}-[0-9]+-[0-9]+', release):
    raise SystemExit('Invalid release identity')
abi = subprocess.check_output(['/usr/bin/node', '-p', 'process.versions.modules'], text=True).strip()
if metadata['node_abi'] != abi or metadata['platform'] != 'linux-x64':
    raise SystemExit('Build/runtime Node ABI or architecture differs')
destination = pathlib.Path('/opt/shipit/backend/releases') / release
destination.parent.mkdir(parents=True, exist_ok=True)
# Recreate from this verified CodeDeploy revision on retries/rollback. The
# running release is never overwritten; it uses a different release directory.
if destination.exists():
    if (destination / 'release.json').read_bytes() != (incoming / 'release.json').read_bytes():
        raise SystemExit('Release identity collision')
else:
    temporary = destination.with_name(release + '.installing')
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(incoming, temporary, symlinks=True)
    temporary.rename(destination)
subprocess.run(['install', '-m', '0644', str(source / 'backend.service'), '/etc/systemd/system/shipit-backend.service'], check=True)
subprocess.run(['install', '-D', '-m', '0755', str(source / 'fetch-secret.sh'), '/usr/local/libexec/shipit-fetch-secret'], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
PY
