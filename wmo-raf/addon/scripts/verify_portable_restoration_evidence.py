#!/usr/bin/env python3
"""Read-only validation of recorded isolated database restoration.

This verifies evidence consistency and selected record/schema comparisons.
It does not authorize an add-on installation.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def verify(args):
    if not CONTAINER.fullmatch(args.container):
        raise ValueError("Unsafe container name")
    for name in (args.db_user, args.original_db, args.restored_db):
        if not IDENTIFIER.fullmatch(name):
            raise ValueError("Unsafe database identifier")
    if args.original_db == args.restored_db:
        raise ValueError("Original and restored databases must differ")
    if not args.restored_db.startswith("che_restore_"):
        raise ValueError("Unexpected restore database name")

    target = args.target.expanduser().absolute()
    manifest = args.manifest.expanduser().absolute()
    evidence = args.evidence.expanduser().absolute()

    for path in (manifest, evidence):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or unsafe evidence file")

    scripts = Path(__file__).resolve().parent
    validator = scripts / "validate_recovery_portable.py"
    result = subprocess.run(
        [sys.executable, str(validator), str(target), str(manifest)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if result.returncode:
        raise ValueError("Recovery manifest verification failed")

    document = json.loads(manifest.read_text())
    report = json.loads(evidence.read_text())

    if not isinstance(report, dict):
        raise ValueError("Invalid restoration evidence structure")

    archive = document["archives"]["database"]
    expected = {
        "schema_version": 1,
        "installation_authorized": False,
        "restoration_completed": True,
        "record_comparison_verified": False,
        "schema_comparison_verified": False,
        "target": str(target),
        "original_database": args.original_db,
        "restored_database": args.restored_db,
        "container": args.container,
        "backup_filename": archive["filename"],
        "backup_sha256": archive["sha256"],
    }

    for name, value in expected.items():
        if type(report.get(name)) is not type(value) or report[name] != value:
            raise ValueError("Restoration evidence mismatch: " + name)

    timestamp = report.get("completed_at_utc")
    if not isinstance(timestamp, str):
        raise ValueError("Missing restoration timestamp")
    moment = datetime.fromisoformat(timestamp)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Restoration timestamp lacks timezone")

    print("PASS: Restoration evidence matches verified backup manifest", flush=True)
    print("PASS: Target, container and database identities match", flush=True)

    arguments = [
        "--container", args.container,
        "--db-user", args.db_user,
        "--original-db", args.original_db,
        "--restored-db", args.restored_db,
    ]

    for label, name in (
        ("CAP record comparison", "compare_portable_restoration.py"),
        ("PostgreSQL schema comparison", "compare_portable_schema.py"),
    ):
        checker = scripts / name
        if checker.is_symlink() or not checker.is_file():
            raise ValueError("Missing or unsafe comparator: " + name)

        result = subprocess.run(
            [sys.executable, str(checker), *arguments],
            capture_output=True, text=True, check=False, timeout=300,
        )
        if result.returncode:
            raise RuntimeError(label + " failed")
        print("PASS:", label, flush=True)

    print("PASS: Restoration evidence and selected database comparisons verified")
    print("NOTE: This does not verify all schemas, roles, permissions or snapshot consistency")
    print("NOTE: Restore provenance is supported by executor evidence, not independently attested")
    print("INSTALLATION NOT AUTHORIZED: Partial restoration verification only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--container", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--original-db", required=True)
    parser.add_argument("--restored-db", required=True)
    args = parser.parse_args()
    try:
        verify(args)
        return 0
    except (
        OSError, ValueError, KeyError, TypeError, RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
