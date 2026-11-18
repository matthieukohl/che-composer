#!/usr/bin/env python3
"""Read-only CHE source installation transaction inventory."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TARGET = ADDON / "test-cap-source"
CAP = TARGET / "capcomposer/src/capcomposer"
COMBINED = ROOT / "wmo-raf/combined/capcomposer/src/capcomposer"
MANIFEST = ADDON / "integration/che_source_manifest.json"

MODIFIED = {
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
}
BRANDING = {
    "config/branding.py",
    "config/static/images/cap_che_composer.png",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not TARGET.is_dir() or TARGET.is_symlink():
        raise RuntimeError("Unsafe or missing test installation")

    manifest = json.loads(MANIFEST.read_text())
    records = manifest["files"]
    if len(records) != 36:
        raise RuntimeError("Unexpected CHE inventory size")

    operations = []

    for record in records:
        relative = Path(record["path"])
        source = ROOT / "che-core" / relative
        destination = CAP / "che" / relative

        if (
            relative.is_absolute()
            or ".." in relative.parts
            or source.is_symlink()
            or not source.is_file()
            or source.stat().st_size != record["size"]
            or digest(source) != record["sha256"]
        ):
            raise RuntimeError("Unsafe CHE source: " + str(relative))

        operations.append(("CREATE", destination))

    for relative in sorted(BRANDING):
        source = COMBINED / relative
        destination = CAP / relative
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("Missing branding source: " + relative)
        operations.append(("CREATE", destination))

    for relative in sorted(MODIFIED):
        destination = CAP / relative
        if destination.is_symlink() or not destination.is_file():
            raise RuntimeError("Unsafe CAP configuration: " + relative)
        operations.append(("MODIFY", destination))

    if len(operations) != 41:
        raise RuntimeError("Unexpected number of file operations")

    destinations = [path for _, path in operations]
    if len(set(destinations)) != len(destinations):
        raise RuntimeError("Duplicate installation destination")

    for operation, destination in operations:
        try:
            destination.relative_to(CAP)
        except ValueError:
            raise RuntimeError("Destination outside test installation")
        for parent in destination.parents:
            if parent == CAP.parent:
                break
            if parent.is_symlink():
                raise RuntimeError("Symbolic-link destination parent")
        if operation == "CREATE" and (
            destination.exists() or destination.is_symlink()
        ):
            raise RuntimeError("Occupied installation destination: " + str(destination))

    planner = ADDON / "scripts/plan_source_changes.py"
    result = subprocess.run(
        [sys.executable, str(planner), str(TARGET)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        print(result.stdout)
        raise RuntimeError("Source-change proposal verification failed")

    print("PASS: 36 CHE files verified for creation")
    print("PASS: 2 branding assets verified for creation")
    print("PASS: 3 CAP configuration files verified for modification")
    print("PASS: Source-change proposals verified")
    print("PASS: No occupied or duplicate destinations")
    print("PASS: Total planned file operations:", len(operations))
    print("DRY RUN ONLY: No installation files modified")
    print("INSTALLATION NOT AUTHORIZED: Transaction and rollback logic pending")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
