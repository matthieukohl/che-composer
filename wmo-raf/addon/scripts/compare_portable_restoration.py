#!/usr/bin/env python3
"""Read-only comparison of original and restored CAP PostgreSQL records.

This is one restoration check, NOT sufficient installation authorization.
"""

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile

TABLES = {
    "django_migrations": "id",
    "auth_user": "id",
    "wagtailcore_page": "id",
    "cap_capalertpage": "page_ptr_id",
}

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def validate_args(args):
    if not CONTAINER.fullmatch(args.container):
        raise ValueError("Invalid PostgreSQL container identifier")
    for value in (args.db_user, args.original_db, args.restored_db):
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("Unsafe PostgreSQL identifier")
    if args.original_db == args.restored_db:
        raise ValueError("Original and restored databases must be different")


def fingerprint(args, database, table, key):
    # Fixed table/key inventory, not user-supplied SQL.
    sql = (
        "COPY (SELECT row_to_json(t)::text FROM "
        f"(SELECT * FROM public.{table} ORDER BY {key}) t) TO STDOUT"
    )

    command = [
        "docker", "exec", args.container,
        "psql", "-X", "-U", args.db_user,
        "-d", database, "-v", "ON_ERROR_STOP=1",
        "-c", sql,
    ]

    digest = hashlib.sha256()
    rows = 0

    # Stream large result sets instead of holding national data in memory.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=errors,
        )
        try:
            for line in process.stdout:
                digest.update(line)
                rows += 1
            process.stdout.close()
            status = process.wait(timeout=120)
        except BaseException:
            process.kill()
            process.wait()
            raise

        if status != 0:
            raise RuntimeError(
                "PostgreSQL read-only inspection failed for "
                + database + "." + table
            )

    return rows, digest.hexdigest()


def compare(args):
    validate_args(args)

    for table, key in TABLES.items():
        original = fingerprint(args, args.original_db, table, key)
        restored = fingerprint(args, args.restored_db, table, key)

        if original != restored:
            raise RuntimeError(
                "Restored records differ: " + table
                + " (original rows=" + str(original[0])
                + ", restored rows=" + str(restored[0]) + ")"
            )

        if table in ("django_migrations", "wagtailcore_page") and original[0] == 0:
            raise RuntimeError("Unexpected empty foundational CAP table: " + table)

        print("PASS: Restored records match:", table,
              "| rows:", original[0], flush=True)

    print("PASS: Four essential CAP tables match original and restored databases")
    print("NOTE: Empty CAP alert tables are allowed")
    print("NOTE: Full schema, sequences, roles, extensions, other tables and")
    print("      independent backup provenance still require verification")
    print("INSTALLATION NOT AUTHORIZED: Partial restoration comparison only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--original-db", required=True)
    parser.add_argument("--restored-db", required=True)
    args = parser.parse_args()

    try:
        compare(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print("FAIL:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
