#!/usr/bin/env python3
"""Read-only CHE transaction inventory for disposable customized CAP workspaces."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TEST_ROOT = (ADDON / "transaction-tests").resolve()
SCRIPTS = ADDON / "scripts"
COMBINED = ROOT / "wmo-raf/combined/capcomposer/src/capcomposer"
CHE_SOURCE = ROOT / "che-core"

MODIFIED = (
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
)
BRANDING = (
    "config/branding.py",
    "config/static/images/cap_che_composer.png",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Invalid relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError("Unsafe relative path")
    return path


def safe_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe source: " + str(path))
    return path.read_bytes()


def plan(workspace):
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("Missing or unsafe workspace")
    workspace = workspace.resolve()

    relative = workspace.relative_to(TEST_ROOT)
    if len(relative.parts) != 1 or not workspace.name.startswith("rollback-"):
        raise ValueError("Only disposable rollback workspaces are supported")

    cap = workspace / "capcomposer/src/capcomposer"
    for parent in (
        workspace / "capcomposer",
        workspace / "capcomposer/src",
        cap,
    ):
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError("Unsafe CAP workspace layout")

    manifest_path = ADDON / "integration/che_source_manifest.json"
    manifest = json.loads(safe_file(manifest_path).decode("utf-8"))
    records = manifest["files"]
    if len(records) != 36:
        raise ValueError("Expected exactly 36 CHE source files")

    operations = []
    seen = set()

    def add(action, destination):
        if destination in seen:
            raise ValueError("Duplicate transaction destination")
        destination.relative_to(cap)
        seen.add(destination)

        current = destination
        while current != cap:
            if current.is_symlink():
                raise ValueError("Symbolic-link destination: " + str(current))
            current = current.parent

        if action == "CREATE" and destination.exists():
            raise ValueError("Occupied CHE destination: " + str(destination))
        if action == "MODIFY" and not destination.is_file():
            raise ValueError("Missing CAP configuration: " + str(destination))

        operations.append((action, destination))

    for record in records:
        relative = safe_relative(record["path"])
        source = CHE_SOURCE / relative
        content = safe_file(source)
        if len(content) != record["size"] or digest(content) != record["sha256"]:
            raise ValueError("CHE source integrity mismatch: " + str(relative))
        add("CREATE", cap / "che" / relative)

    for name in BRANDING:
        safe_file(COMBINED / safe_relative(name))
        add("CREATE", cap / name)

    for name in MODIFIED:
        add("MODIFY", cap / name)

    if len(operations) != 41:
        raise ValueError("Unexpected transaction operation count")

    planner = SCRIPTS / "plan_customized_source_changes.py"
    if planner.is_symlink() or not planner.is_file():
        raise ValueError("Customized source planner unavailable")

    result = subprocess.run(
        [sys.executable, str(planner), str(workspace), "--no-diff"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            "Country-specific patch planning failed: "
            + (result.stdout.strip() or result.stderr.strip())
        )

    print("PASS: 36 CHE source files verified")
    print("PASS: 2 branding assets verified for creation")
    print("PASS: 3 national CAP configuration patches validated")
    print("PASS: No duplicate, occupied or unsafe destinations")
    print("PASS: Total planned operations:", len(operations))
    print("DRY RUN ONLY: No installation files modified")
    print("INSTALLATION NOT AUTHORIZED: Transaction planning only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    plan(args.workspace.expanduser())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
