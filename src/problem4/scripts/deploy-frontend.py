"""Publish immutable SPA assets, then a versioned entrypoint; recover on failure."""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from urllib.parse import quote, urlparse

from aws_common import aws, catch_termination, fetch, invalidate, public_url, record, required, retry, sha256


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            src = dict(attrs).get("src")
            if src:
                self.sources.append(src)


def same_bytes(url, expected):
    if hashlib.sha256(fetch(url)).hexdigest() != expected:
        raise ValueError(f"Public content does not match release artifact: {url}")


def main():
    directory = Path(sys.argv[1])
    release = json.loads((directory / "release.json").read_text())
    bucket = required("FRONTEND_BUCKET")
    distribution = required("CLOUDFRONT_DISTRIBUTION")
    environment = required("DEPLOY_ENVIRONMENT")
    url = public_url()
    evidence = {"application": "frontend", "environment": environment, "release": release, "bucket": bucket}
    record(evidence, status="preflight")
    previous = None
    previous_hash = None
    published = None
    attempted = False
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        try:
            if aws("s3api", "get-bucket-versioning", "--bucket", bucket).get("Status") != "Enabled":
                raise ValueError("Frontend bucket versioning must be enabled")
            # Listing distinguishes no object from permission/network failure.
            versions = aws("s3api", "list-object-versions", "--bucket", bucket,
                           "--prefix", "index.html", "--max-keys", "1", "--no-paginate")
            for version in versions.get("Versions", []):
                if version["Key"] == "index.html" and version["IsLatest"]:
                    previous = version["VersionId"]
            if previous:
                aws("s3api", "get-object", "--bucket", bucket, "--key", "index.html",
                    "--version-id", previous, root / "previous-index.html")
                previous_hash = sha256(root / "previous-index.html")
            if environment.endswith("production") and not previous:
                raise ValueError("Bootstrap a known-good frontend index before production promotion")
            record(evidence, previous_index_version=previous, previous_index_sha256=previous_hash)
            with tarfile.open(directory / "bundle.tgz") as archive:
                archive.extractall(root / "release", filter="data")
            dist = root / "release/dist"
            index = dist / "index.html"
            if not index.is_file():
                raise ValueError("Missing dist/index.html")
            parser = Scripts()
            parser.feed(index.read_text())
            prefix = f'/releases/{release["release_id"]}/'
            sources = [src for src in parser.sources if src.startswith(prefix) and urlparse(src).path.endswith(".js")]
            if not sources:
                raise ValueError("SPA must reference a JavaScript entrypoint under its immutable release prefix")
            asset_url = urlparse(sources[0]).path
            asset = (dist / asset_url.removeprefix(prefix)).resolve()
            if not asset.is_relative_to(dist.resolve()) or not asset.is_file():
                raise ValueError("Script asset is missing or outside the artifact")
            # Same release ID may be retried with identical bytes. No old prefix
            # or bucket object is deleted; root index is switched only afterward.
            aws("s3", "sync", str(dist) + "/", f's3://{bucket}/releases/{release["release_id"]}/',
                "--cache-control", "public,max-age=31536000,immutable", "--sse", "AES256",
                "--no-progress", "--only-show-errors", raw=True, timeout=300)
            attempted = True
            result = aws("s3api", "put-object", "--bucket", bucket, "--key", "index.html", "--body", index,
                         "--content-type", "text/html; charset=utf-8", "--cache-control", "no-cache,max-age=0,must-revalidate",
                         "--metadata", json.dumps({"release-id": release["release_id"], "commit": release["commit"]}),
                         "--server-side-encryption", "AES256")
            published = result["VersionId"]
            record(evidence, status="published", index_version=published, index_sha256=sha256(index))
            invalidation = invalidate(distribution)
            retry(lambda: same_bytes(url + "/index.html", sha256(index)))
            retry(lambda: same_bytes(url + asset_url, sha256(asset)))
            record(evidence, status="succeeded", invalidation_id=invalidation)
        except BaseException as failure:
            record(evidence, status="failed", error=str(failure))
            if attempted:
                try:
                    current = aws("s3api", "head-object", "--bucket", bucket, "--key", "index.html")
                    if current.get("Metadata", {}).get("release-id") != release["release_id"]:
                        raise RuntimeError("Entrypoint belongs to another writer; coordinate recovery")
                    if published and current["VersionId"] != published:
                        raise RuntimeError("Entrypoint version changed; coordinate recovery")
                    published = current["VersionId"]
                    if previous:
                        restored = aws("s3api", "copy-object", "--bucket", bucket, "--key", "index.html",
                                       "--copy-source", f'{bucket}/index.html?versionId={quote(previous, safe="")}',
                                       "--metadata-directive", "REPLACE", "--content-type", "text/html; charset=utf-8",
                                       "--cache-control", "no-cache,max-age=0,must-revalidate",
                                       "--server-side-encryption", "AES256")
                        record(evidence, restored_index_version=restored["VersionId"])
                    else:
                        # Initial staging publish: restore absence, never pretend
                        # this is a rollback to a known-good website.
                        aws("s3api", "delete-object", "--bucket", bucket, "--key", "index.html", "--version-id", published)
                    invalidate(distribution)
                    if previous:
                        retry(lambda: same_bytes(url + "/index.html", previous_hash))
                    record(evidence, recovery="previous index restored" if previous else "initial publish removed; no known-good site")
                except BaseException as recovery_failure:
                    record(evidence, recovery="unconfirmed: operator action required", recovery_error=str(recovery_failure))
            raise


if __name__ == "__main__":
    catch_termination()
    main()
