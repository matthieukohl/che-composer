#!/usr/bin/env python3
"""Read-only CHE add-on recovery manifest validation.

Validates artifact references and checksums, not restoration evidence.
Does not authorize installation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REQUIRED = {"database", "configuration_media", "source"}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Validate CHE add-on recovery artifacts"
    )
    parser.add_argument("target", help="CAP Composer source directory")
    parser.add_argument("manifest", help="Recovery manifest JSON file")
    args = parser.parse_args()

    release_root = Path(__file__).resolve().parents[3]
    target = Path(args.target).expanduser().resolve()
    manifest = Path(args.manifest).expanduser()

    if not target.is_dir():
        print("FAIL: Target directory missing")
        return 1

    if manifest.is_symlink() or not manifest.is_file():
        print("FAIL: Recovery manifest missing or unsafe")
        return 1

    try:
        document = json.loads(manifest.read_text())
    except (OSError, ValueError):
        print("FAIL: Cannot read recovery manifest")
        return 1

    if not isinstance(document, dict):
        print("FAIL: Invalid manifest structure")
        return 1

    if document.get("schema_version") != 1:
        print("FAIL: Unsupported manifest schema")
        return 1

    recorded_target = document.get("target")
    if not isinstance(recorded_target, str):
        print("FAIL: Invalid target reference")
        return 1

    if (release_root / recorded_target).resolve() != target:
        print("FAIL: Manifest belongs to a different installation")
        return 1

    archives = document.get("archives")
    if not isinstance(archives, dict) or set(archives) != REQUIRED:
        print("FAIL: Incorrect backup artifact inventory")
        return 1

    backup_dir = manifest.parent.resolve()

    for category in sorted(REQUIRED):
        record = archives[category]
        if not isinstance(record, dict):
            print("FAIL: Invalid artifact record:", category)
            return 1

        filename = record.get("filename")
        expected = record.get("sha256")

        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or filename in {".", ".."}
            or not isinstance(expected, str)
            or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)
        ):
            print("FAIL: Unsafe artifact reference:", category)
            return 1

        path = backup_dir / filename
        if path.is_symlink() or not path.is_file():
            print("FAIL: Backup archive missing or unsafe:", category)
            return 1

        try:
            actual = sha256_file(path)
        except OSError:
            print("FAIL: Cannot read backup archive:", category)
            return 1

        if actual != expected:
            print("FAIL: Backup checksum mismatch:", category)
            return 1

        print("PASS: Recovery artifact checksum:", category)

    if document.get("installation_authorized") is not False:
        print("FAIL: Recovery evidence must not claim installation authorization")
        return 1

    print("PASS: Manifest target and artifact inventory verified")
    print("NOTE: Archive readability and restoration evidence require separate checks")
    print("INSTALLATION NOT AUTHORIZED: Recovery manifest validation only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
