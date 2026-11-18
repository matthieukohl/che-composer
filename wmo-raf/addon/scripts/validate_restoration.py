#!/usr/bin/env python3
"""Read-only restoration evidence validator for the isolated CHE add-on test.

Not a production backup authorization mechanism.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

EXPECTED_ORIGINAL = "chetest_addon"
EXPECTED_RESTORED = "chetest_addon_restore_final"
EXPECTED_CONTAINER = "chetest_addon_db"

TABLES = {
    "django_migrations": "id",
    "auth_user": "id",
    "wagtailcore_page": "id",
    "cap_capalertpage": "page_ptr_id",
}


def query(database, sql):
    command = [
        "docker", "exec", EXPECTED_CONTAINER,
        "psql", "-X", "-U", EXPECTED_ORIGINAL,
        "-d", database, "-At",
        "-v", "ON_ERROR_STOP=1", "-c", sql,
    ]
    result = subprocess.run(
        command, capture_output=True, check=False
    )
    if result.returncode:
        raise RuntimeError("Database inspection failed: " + database)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("evidence")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser()
    evidence_path = Path(args.evidence).expanduser()

    for path in (manifest_path, evidence_path):
        if path.is_symlink() or not path.is_file():
            print("FAIL: Missing or unsafe evidence file")
            return 1

    try:
        manifest = json.loads(manifest_path.read_text())
        evidence = json.loads(evidence_path.read_text())
    except (OSError, ValueError):
        print("FAIL: Cannot parse recovery evidence")
        return 1

    if not isinstance(manifest, dict) or not isinstance(evidence, dict):
        print("FAIL: Invalid recovery evidence structure")
        return 1

    try:
        database_record = manifest["archives"]["database"]
        expected_hash = database_record["sha256"]
        archive_name = database_record["filename"]
    except (KeyError, TypeError):
        print("FAIL: Database backup metadata missing")
        return 1

    if (
        evidence.get("schema_version") != 1
        or evidence.get("installation_authorized") is not False
        or evidence.get("original_database") != EXPECTED_ORIGINAL
        or evidence.get("restored_database") != EXPECTED_RESTORED
        or evidence.get("backup_filename") != archive_name
        or evidence.get("backup_sha256") != expected_hash
    ):
        print("FAIL: Restoration evidence does not match backup manifest")
        return 1

    backup = manifest_path.parent / archive_name
    if (
        not isinstance(archive_name, str)
        or Path(archive_name).name != archive_name
        or backup.is_symlink()
        or not backup.is_file()
    ):
        print("FAIL: Invalid database backup reference")
        return 1

    digest = hashlib.sha256()
    with backup.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    if digest.hexdigest() != expected_hash:
        print("FAIL: Database backup checksum mismatch")
        return 1

    print("PASS: Evidence references the verified database backup")

    try:
        for table, key in TABLES.items():
            sql = (
                "SELECT row_to_json(t)::text FROM "
                f"(SELECT * FROM public.{table} ORDER BY {key}) t;"
            )
            original = query(EXPECTED_ORIGINAL, sql)
            restored = query(EXPECTED_RESTORED, sql)
            if original != restored:
                print("FAIL: Restored records differ:", table)
                return 1
            print("PASS: Restored records match:", table)

        counts_sql = """
SELECT
 (SELECT count(*) FROM django_migrations),
 (SELECT count(*) FROM cap_capalertpage),
 (SELECT count(*) FROM auth_user WHERE is_superuser),
 (SELECT count(*) FROM wagtailcore_page
    WHERE id=5 AND slug='che-addon-preservation-test'),
 (SELECT count(*) FROM wagtailcore_page
    WHERE id=4 AND slug='che-addon-test-alerts');
"""
        for database in (EXPECTED_ORIGINAL, EXPECTED_RESTORED):
            if query(database, counts_sql).strip() != b"324|1|1|1|1":
                print("FAIL: Unexpected CAP preservation baseline:", database)
                return 1

    except (OSError, RuntimeError):
        print("FAIL: Live database verification unavailable")
        return 1

    print("PASS: Live CAP preservation baseline verified")
    print("NOTE: Full schema, sequence and backup provenance checks remain separate")
    print("INSTALLATION NOT AUTHORIZED: Restoration validation only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
