#!/usr/bin/env python3
"""Read-only plan for an isolated PostgreSQL restoration test."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def plan(args):
    if not CONTAINER.fullmatch(args.container):
        raise ValueError("Unsafe container identifier")

    for value in (args.db_user, args.original_db, args.restored_db):
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("Unsafe PostgreSQL identifier")

    if args.original_db == args.restored_db:
        raise ValueError("Original and restored databases must differ")

    if not args.restored_db.startswith("che_restore_"):
        raise ValueError("Restore database must use che_restore_ prefix")

    target = args.target.expanduser().absolute()
    manifest = args.manifest.expanduser().absolute()
    validator = Path(__file__).resolve().parent / "validate_recovery_portable.py"

    result = subprocess.run(
        [sys.executable, str(validator), str(target), str(manifest)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if result.returncode:
        raise ValueError(
            "Recovery manifest or backup checksum verification failed"
        )

    document = json.loads(manifest.read_text())
    backup = document["archives"]["database"]

    sql = (
        "SELECT 1 FROM pg_catalog.pg_database WHERE datname = '"
        + args.restored_db + "';"
    )

    result = subprocess.run(
        [
            "docker", "exec", args.container,
            "psql", "-X", "-At", "-v", "ON_ERROR_STOP=1",
            "-U", args.db_user, "-d", "postgres", "-c", sql,
        ],
        capture_output=True, check=False, timeout=30,
    )

    if result.returncode:
        raise ValueError("Cannot inspect existing PostgreSQL databases")
    if result.stdout.strip() == b"1":
        raise ValueError("Restore destination database already exists")
    if result.stdout.strip():
        raise ValueError("Unexpected database inspection result")

    print("PASS: Recovery manifest and backup checksums verified")
    print("PASS: Original and restored database names are distinct")
    print("PASS: Restore destination database does not currently exist")
    print("PASS: Reserved restore-database prefix verified")
    print("Verified backup SHA-256:", backup["sha256"])
    print("NOTE: Database nonexistence must be enforced again at creation time")
    print("DRY RUN ONLY: No database created or restored")
    print("INSTALLATION NOT AUTHORIZED: Planning only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--container", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--original-db", required=True)
    parser.add_argument("--restored-db", required=True)
    args = parser.parse_args()

    try:
        plan(args)
        return 0
    except (
        OSError, ValueError, KeyError, TypeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
