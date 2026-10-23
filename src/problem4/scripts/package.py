"""Application contract and immutable artifact packaging. No AWS credentials needed."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile


def digest(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def contract(app):
    root = Path("apps") / app
    if not (root / "package-lock.json").is_file():
        raise ValueError(f"Supply {root}/package-lock.json and application source first")
    package = json.loads((root / "package.json").read_text())
    for script in ("lint", "test", "build"):
        if not package.get("scripts", {}).get(script):
            raise ValueError(f"{root}/package.json must define a noninteractive {script} script")
    return root


def build(app):
    root = contract(app)
    commit = os.environ["GITHUB_SHA"]
    release_id = f'{commit}-{os.environ["GITHUB_RUN_ID"]}-{os.environ["GITHUB_RUN_ATTEMPT"]}'
    if not re.fullmatch(r"[0-9a-f]{40}-[0-9]+-[0-9]+", release_id):
        raise ValueError("Invalid release identity")
    entry = "dist/server.js" if app == "backend" else "dist/index.html"
    if not (root / entry).is_file():
        raise ValueError(f"Build must produce {root / entry}")
    metadata = {
        "app": app, "commit": commit, "release_id": release_id,
        "repository": os.environ["GITHUB_REPOSITORY"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "node_abi": subprocess.check_output(["node", "-p", "process.versions.modules"], text=True).strip(),
        "platform": "linux-x64", "os": "ubuntu-24.04",
    }
    output = Path("output") / app
    output.mkdir(parents=True, exist_ok=False)
    (output / "release.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        payload = stage / "payload" if app == "backend" else stage
        payload.mkdir(exist_ok=True)
        shutil.copytree(root / "dist", payload / "dist", symlinks=True)
        if app == "backend":
            for name in ("package.json", "package-lock.json"):
                shutil.copy2(root / name, payload / name)
            if (root / "node_modules").exists():
                shutil.copytree(root / "node_modules", payload / "node_modules", symlinks=True)
            shutil.copytree("tasks/problem4/backend", stage, dirs_exist_ok=True)
            shutil.copy2("tasks/problem4/backend/launcher.cjs", payload / "launcher.cjs")
            for hook in (stage / "hooks").glob("*.sh"):
                hook.chmod(0o755)
        shutil.copy2(output / "release.json", payload / "release.json")
        shutil.copy2(root / "sbom.json", payload / "sbom.json")
        # Includes all files and symlinks; verification at the artifact boundary
        # checks the tar bytes, preserving native node_modules symlinks.
        with tarfile.open(output / "bundle.tgz", "w:gz") as archive:
            for path in sorted(stage.iterdir()):
                archive.add(path, arcname=path.name)
    (output / "SHA256SUMS").write_text("".join(
        f"{digest(output / name)}  {name}\n" for name in ("bundle.tgz", "release.json")
    ))
    print(f"Packaged {app} release {release_id}")


def verify(app, directory):
    root = Path(directory)
    lines = (root / "SHA256SUMS").read_text().splitlines()
    if len(lines) != 2:
        raise ValueError("Expected exactly two artifact checksums")
    expected = {}
    for line in lines:
        checksum, name = line.split("  ", 1)
        if name not in ("bundle.tgz", "release.json") or name in expected:
            raise ValueError("Unexpected checksum path")
        expected[name] = checksum
        if digest(root / name) != checksum:
            raise ValueError(f"Checksum mismatch for {name}")
    metadata = json.loads((root / "release.json").read_text())
    if metadata["app"] != app or metadata["commit"] != os.environ["GITHUB_SHA"]:
        raise ValueError("Artifact belongs to another application or commit")
    if metadata["repository"] != os.environ["GITHUB_REPOSITORY"]:
        raise ValueError("Artifact belongs to another repository")
    if metadata["run_id"] != os.environ["GITHUB_RUN_ID"]:
        raise ValueError("Artifact belongs to another workflow run")
    if not re.fullmatch(r"[0-9a-f]{40}-[0-9]+-[0-9]+", metadata["release_id"]):
        raise ValueError("Invalid release ID")
    print(f'Verified {metadata["release_id"]}')


if __name__ == "__main__":
    operation, application, *rest = sys.argv[1:]
    if application not in ("backend", "frontend"):
        raise ValueError("Unknown application")
    if operation == "contract":
        contract(application)
    elif operation == "build":
        build(application)
    elif operation == "verify":
        verify(application, rest[0])
    else:
        raise ValueError("Unknown operation")
