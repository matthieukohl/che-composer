#!/usr/bin/env python3
"""Controlled PostgreSQL test restoration. Never overwrites or drops databases.

Requires explicit --execute. Successful restoration is NOT proof of complete
database equivalence; record and schema comparisons are separate requirements.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def execute(args):
    if not args.execute:
        raise ValueError("Explicit --execute flag required")
    if not CONTAINER.fullmatch(args.container):
        raise ValueError("Unsafe container identifier")
    for value in (args.db_user, args.original_db, args.restored_db):
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("Unsafe database identifier")
    if args.original_db == args.restored_db:
        raise ValueError("Original and restored databases must differ")
    if not args.restored_db.startswith("che_restore_"):
        raise ValueError("Restore destination must use che_restore_ prefix")

    target = args.target.expanduser().absolute()
    manifest = args.manifest.expanduser().absolute()
    evidence = args.evidence.expanduser().absolute()

    if evidence.exists() or evidence.is_symlink():
        raise ValueError("Restoration evidence destination already occupied")
    if evidence.parent.is_symlink() or not evidence.parent.is_dir():
        raise ValueError("Unsafe evidence directory")

    # Perform the complete read-only planning gate before writing anything.
    planner = Path(__file__).resolve().parent / "plan_isolated_restoration.py"
    result = subprocess.run(
        [
            sys.executable, str(planner), str(target), str(manifest),
            "--container", args.container,
            "--db-user", args.db_user,
            "--original-db", args.original_db,
            "--restored-db", args.restored_db,
        ],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if result.returncode:
        raise RuntimeError("Isolated restoration planning failed")

    document = json.loads(manifest.read_text())
    record = document["archives"]["database"]
    archive = manifest.parent / record["filename"]
    expected = record["sha256"]

    if archive.is_symlink() or not archive.is_file():
        raise ValueError("Unsafe database archive")
    if digest_file(archive) != expected:
        raise ValueError("Database archive changed after planning")

    # createdb fails if the destination already exists. No DROP or overwrite.
    create = subprocess.run(
        [
            "docker", "exec", args.container, "createdb",
            "-U", args.db_user, "--template=template0",
            args.restored_db,
        ],
        capture_output=True, check=False, timeout=120,
    )
    if create.returncode:
        raise RuntimeError("Could not create new restore database")

    print("PASS: New isolated restore database created", flush=True)

    # Restore into the newly created database; never use --create or --clean.
    # Ownership and ACL restoration need separate review for national systems.
    with archive.open("rb") as stream:
        restore = subprocess.run(
            [
                "docker", "exec", "-i", args.container,
                "pg_restore", "--exit-on-error",
                "--no-owner", "--no-acl",
                "-U", args.db_user, "-d", args.restored_db,
            ],
            stdin=stream,
            capture_output=True, check=False, timeout=600,
        )

    if restore.returncode:
        raise RuntimeError(
            "Database restore failed; isolated database retained for inspection"
        )

    if digest_file(archive) != expected:
        raise RuntimeError("Archive changed during restoration")

    identity = subprocess.run(
        [
            "docker", "exec", args.container,
            "psql", "-X", "-At", "-v", "ON_ERROR_STOP=1",
            "-U", args.db_user, "-d", args.restored_db,
            "-c", "SELECT current_database();",
        ],
        capture_output=True, check=False, timeout=30,
    )
    if (
        identity.returncode
        or identity.stdout.strip().decode("utf-8") != args.restored_db
    ):
        raise RuntimeError("Cannot verify restored database identity")

    record = {
        "schema_version": 1,
        "installation_authorized": False,
        "restoration_completed": True,
        "record_comparison_verified": False,
        "schema_comparison_verified": False,
        "target": str(target),
        "original_database": args.original_db,
        "restored_database": args.restored_db,
        "container": args.container,
        "backup_filename": archive.name,
        "backup_sha256": expected,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    # Exclusive creation: never replace existing evidence.
    with evidence.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")

    print("PASS: Restoration command completed successfully")
    print("PASS: Restored database identity verified")
    print("PASS: Backup checksum verified before and after restoration")
    print("PASS: Restoration evidence written")
    print("NOTE: CAP record and PostgreSQL schema verification still required")
    print("INSTALLATION NOT AUTHORIZED: Restoration alone is insufficient")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--container", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--original-db", required=True)
    parser.add_argument("--restored-db", required=True)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        execute(args)
        return 0
    except (
        OSError, ValueError, KeyError, TypeError, RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
