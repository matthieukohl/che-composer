#!/usr/bin/env python3
"""Read-only recovery artifact validation for portable CHE installations."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

REQUIRED = {"database", "configuration_media", "source"}


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(target, manifest):
    if target.is_symlink() or not target.is_dir():
        raise ValueError("Missing or unsafe CAP Composer installation")
    target = target.resolve()

    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Missing or unsafe recovery manifest")

    document = json.loads(manifest.read_text())
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported recovery manifest schema")

    recorded = document.get("target")
    if not isinstance(recorded, str) or not recorded:
        raise ValueError("Invalid installation target reference")

    recorded_path = Path(recorded).expanduser()
    if not recorded_path.is_absolute():
        raise ValueError(
            "Portable recovery manifest requires an absolute installation path"
        )
    if recorded_path.is_symlink() or recorded_path.resolve() != target:
        raise ValueError("Recovery manifest belongs to a different installation")

    archives = document.get("archives")
    if not isinstance(archives, dict) or set(archives) != REQUIRED:
        raise ValueError("Incorrect backup artifact inventory")

    if document.get("installation_authorized") is not False:
        raise ValueError("Recovery manifest must not authorize installation")

    for category in sorted(REQUIRED):
        record = archives[category]
        if not isinstance(record, dict):
            raise ValueError("Invalid backup record: " + category)

        filename = record.get("filename")
        expected = record.get("sha256")
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or filename in (".", "..")
            or not isinstance(expected, str)
            or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)
        ):
            raise ValueError("Unsafe backup reference: " + category)

        archive = manifest.parent / filename
        if archive.is_symlink() or not archive.is_file():
            raise ValueError("Missing or unsafe backup: " + category)
        if digest_file(archive) != expected:
            raise ValueError("Backup checksum mismatch: " + category)

        print("PASS: Verified recovery artifact:", category)

    print("PASS: Recovery manifest matches the selected installation")
    print("NOTE: Database archive readability and restoration are separate checks")
    print("INSTALLATION NOT AUTHORIZED: Recovery artifact validation only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    check(args.target.expanduser().absolute(), args.manifest.expanduser())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
