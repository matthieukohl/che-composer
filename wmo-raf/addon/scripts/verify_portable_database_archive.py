#!/usr/bin/env python3
"""Read-only PostgreSQL backup archive inspection; not restoration proof."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def check(target, manifest, container):
    if not CONTAINER.fullmatch(container):
        raise ValueError("Unsafe PostgreSQL container identifier")

    validator = Path(__file__).resolve().parent / "validate_recovery_portable.py"
    if validator.is_symlink() or not validator.is_file():
        raise ValueError("Portable recovery validator unavailable")

    result = subprocess.run(
        [sys.executable, str(validator), str(target), str(manifest)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError(
            "Recovery manifest verification failed: "
            + (result.stdout.strip().splitlines()[-1] if result.stdout.strip()
               else "validator unavailable")
        )
    print("PASS: Recovery manifest and all archive checksums verified")

    document = json.loads(manifest.read_text())
    record = document["archives"]["database"]
    backup = manifest.parent / record["filename"]

    if backup.is_symlink() or not backup.is_file():
        raise ValueError("Missing or unsafe database archive")

    # pg_restore --list examines the archive; it does not restore data.
    command = ["docker", "exec", "-i", container, "pg_restore", "--list"]
    with backup.open("rb") as stream:
        inspected = subprocess.run(
            command,
            stdin=stream,
            capture_output=True,
            check=False,
            timeout=120,
        )

    if inspected.returncode:
        raise ValueError("PostgreSQL cannot read the database backup archive")

    listing = inspected.stdout.decode("utf-8", errors="replace").splitlines()
    entries = [
        line for line in listing
        if line.strip() and not line.lstrip().startswith(";")
    ]
    if not entries:
        raise ValueError("Database backup has no visible restore inventory")

    print("PASS: PostgreSQL archive inspection succeeded")
    print("PASS: Archive contains restore inventory entries:", len(entries))
    print("NOTE: Archive inspection does not demonstrate a successful restore")
    print("NOTE: Backup provenance and independent restoration remain required")
    print("INSTALLATION NOT AUTHORIZED: Archive verification only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--container", required=True)
    args = parser.parse_args()
    try:
        check(
            args.target.expanduser().absolute(),
            args.manifest.expanduser(),
            args.container,
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
