#!/usr/bin/env python3
"""Render the numbered Mermaid sources; never execute deployment/application code."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[3]
DIAGRAMS = REPO / "tasks/problem4/01.diagrams"
CLI_VERSION = "11.16.0"


def main():
    executable = os.environ.get("MMDC_BIN") or shutil.which("mmdc")
    if executable:
        cli = [executable]
    elif shutil.which("npx"):
        cli = ["npx", "--yes", "--package", f"@mermaid-js/mermaid-cli@{CLI_VERSION}", "mmdc"]
    else:
        raise SystemExit("Supply MMDC_BIN or install Node/npm and Chrome/Chromium")
    browser = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not browser and chrome.is_file():
        browser = str(chrome)
    with tempfile.TemporaryDirectory(prefix="problem4-mermaid-") as temporary:
        config = {"userDataDir": str(Path(temporary) / "browser-profile")}
        if browser:
            config["executablePath"] = browser
        puppeteer = Path(temporary) / "puppeteer.json"
        puppeteer.write_text(json.dumps(config))
        for source in sorted(DIAGRAMS.glob("[0-9][0-9].*.mmd")):
            for extension in ("svg", "png"):
                destination = source.with_suffix(f".{extension}")
                print(f"Rendering {destination.relative_to(REPO)}", flush=True)
                subprocess.run(cli + [
                    "--input", str(source), "--output", str(destination),
                    "--configFile", str(DIAGRAMS / "mermaid-config.json"),
                    "--puppeteerConfigFile", str(puppeteer), "--backgroundColor", "white",
                    "--width", "2400", "--scale", "2",
                ], cwd=REPO, check=True)


if __name__ == "__main__":
    main()
