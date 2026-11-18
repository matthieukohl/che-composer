#!/usr/bin/env python3
"""CHE source transaction engine — test-only preparation stage.

This version validates a disposable workspace and prepares a file inventory.
It does not perform file writes, installation, or rollback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TEST_ROOT = ADDON / "transaction-tests"
CHE_SOURCE = ROOT / "che-core"
COMBINED = ROOT / "wmo-raf/combined/capcomposer/src/capcomposer"

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


def safe_relative(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Invalid relative path")

    relative = Path(name)

    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != name
    ):
        raise ValueError("Unsafe relative path")

    return relative


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a disposable CHE source transaction"
    )
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()

    supplied = Path(args.workspace).expanduser()

    if supplied.is_symlink() or not supplied.is_dir():
        print("FAIL: Workspace missing or unsafe")
        return 1

    workspace = supplied.resolve()
    test_root = TEST_ROOT.resolve()

    try:
        relative_workspace = workspace.relative_to(test_root)
    except ValueError:
        print("FAIL: Workspace is outside transaction-tests")
        return 1

    if len(relative_workspace.parts) != 1 or not workspace.name.startswith("rollback-"):
        print("FAIL: Workspace is not a dedicated rollback test directory")
        return 1

    cap = workspace / "capcomposer/src/capcomposer"

    if not cap.is_dir() or cap.is_symlink():
        print("FAIL: Disposable CAP directory missing or unsafe")
        return 1

    source_manifest = ADDON / "integration/che_source_manifest.json"
    upstream_manifest = ADDON / "integration/upstream_manifest.json"

    if source_manifest.is_symlink() or upstream_manifest.is_symlink():
        print("FAIL: Unsafe source manifest")
        return 1

    source_records = json.loads(source_manifest.read_text())["files"]
    upstream_hashes = json.loads(upstream_manifest.read_text())["sha256"]

    if len(source_records) != 36:
        print("FAIL: Unexpected CHE source inventory")
        return 1

    operations = []
    destinations = set()

    def add_operation(action, destination, content):
        if destination in destinations:
            raise ValueError("Duplicate destination")

        destination.relative_to(cap)
        destinations.add(destination)

        for parent in destination.parents:
            if parent == workspace.parent:
                break
            if parent.is_symlink():
                raise ValueError("Symbolic-link destination parent")

        if destination.is_symlink():
            raise ValueError("Symbolic-link destination")

        if action == "CREATE" and destination.exists():
            raise ValueError("Create destination already occupied")

        if action == "MODIFY" and not destination.is_file():
            raise ValueError("Modification destination missing")

        operations.append((action, destination, digest(content)))

    for record in source_records:
        relative = safe_relative(record["path"])
        source = CHE_SOURCE / relative

        if source.is_symlink() or not source.is_file():
            raise ValueError("Missing or unsafe CHE source")

        content = source.read_bytes()

        if (
            len(content) != record["size"]
            or digest(content) != record["sha256"]
        ):
            raise ValueError("CHE source checksum mismatch")

        add_operation("CREATE", cap / "che" / relative, content)

    for name in BRANDING:
        relative = safe_relative(name)
        source = COMBINED / relative

        if source.is_symlink() or not source.is_file():
            raise ValueError("Missing or unsafe branding source")

        add_operation("CREATE", cap / relative, source.read_bytes())

    for name in MODIFIED:
        relative = safe_relative(name)
        destination = cap / relative
        reference = COMBINED / relative
        upstream_key = "capcomposer/src/capcomposer/" + name

        if destination.is_symlink() or not destination.is_file():
            raise ValueError("Missing or unsafe CAP configuration")

        if digest(destination.read_bytes()) != upstream_hashes.get(upstream_key):
            raise ValueError("Original CAP configuration checksum mismatch")

        if reference.is_symlink() or not reference.is_file():
            raise ValueError("Missing or unsafe combined reference")

        add_operation("MODIFY", destination, reference.read_bytes())

    if len(operations) != 41:
        raise ValueError("Unexpected transaction size")

    print("PASS: Disposable workspace verified:", workspace.name)
    print("PASS: 36 CHE file creation operations prepared")
    print("PASS: 2 branding file creation operations prepared")
    print("PASS: 3 CAP configuration modifications prepared")
    print("PASS: Original CAP configuration checksums verified")
    print("PASS: No occupied or duplicate destinations")
    print("PASS: Total prepared operations:", len(operations))
    print("PREPARATION ONLY: No source files modified")
    print("INSTALLATION DISABLED: Transaction execution and rollback not implemented")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL: Transaction preparation:", exc)
        sys.exit(1)
