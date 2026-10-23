"""Small AWS CLI adapter: no SDK dependency, bounded calls, persistent evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def required(name):
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"Missing environment setting: {name}")
    return value


def aws(*arguments, raw=False, timeout=60):
    command = ["aws", *map(str, arguments), "--no-cli-pager", "--cli-connect-timeout", "5", "--cli-read-timeout", "30"]
    if not raw:
        command += ["--output", "json"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout,
                            env={**os.environ, "AWS_MAX_ATTEMPTS": "3"})
    if result.returncode:
        raise RuntimeError(f"AWS {arguments[0]} {arguments[1]} failed: {result.stderr.strip()}")
    return result.stdout if raw else json.loads(result.stdout or "{}")


def record(data, **updates):
    data.update(updates)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    Path("deployment-record.json").write_text(json.dumps(data, indent=2) + "\n")


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def public_url():
    value = required("PUBLIC_URL").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("PUBLIC_URL must be a public HTTPS origin without credentials/query")
    return value


def fetch(url):
    request = Request(url, headers={"Accept-Encoding": "identity", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP status: {response.status}")
        return response.read()


def retry(operation, attempts=6):
    for attempt in range(attempts):
        try:
            return operation()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(5)


def catch_termination():
    def interrupted(signum, frame):
        # Ignore subsequent cancellation signals while attempting recovery.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise InterruptedError(f"Termination signal {signum}; attempting recovery")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)


def invalidate(distribution):
    result = aws("cloudfront", "create-invalidation", "--distribution-id", distribution,
                 "--paths", "/", "/index.html")
    identity = result["Invalidation"]["Id"]
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        state = aws("cloudfront", "get-invalidation", "--distribution-id", distribution, "--id", identity)
        if state["Invalidation"]["Status"] == "Completed":
            return identity
        time.sleep(10)
    raise TimeoutError(f"CloudFront invalidation {identity} exceeded 15 minutes")
