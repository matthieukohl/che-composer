#!/usr/bin/env python3
"""Read-only verification of the CHE application source inventory."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "che-core"
MANIFEST = ROOT / "wmo-raf/addon/integration/che_source_manifest.json"


def main():
    if MANIFEST.is_symlink() or not MANIFEST.is_file():
        print("FAIL: CHE source manifest missing or unsafe")
        return 1

    try:
        document = json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        print("FAIL: Cannot read CHE source manifest")
        return 1

    if not isinstance(document, dict) or (
        document.get("schema_version") != 1
        or document.get("component") != "capcomposer.che"
        or document.get("source") != "che-core"
        or document.get("destination") != "capcomposer/src/capcomposer/che"
    ):
        print("FAIL: Invalid CHE source manifest metadata")
        return 1

    records = document.get("files")
    if not isinstance(records, list) or len(records) != 36:
        print("FAIL: Unexpected CHE source file inventory")
        return 1

    expected = {}

    for record in records:
        if not isinstance(record, dict):
            print("FAIL: Invalid CHE source file record")
            return 1

        name = record.get("path")
        size = record.get("size")
        checksum = record.get("sha256")

        if not isinstance(name, str) or not name:
            print("FAIL: Invalid CHE source path")
            return 1

        relative = Path(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or relative.as_posix() != name
            or name in expected
        ):
            print("FAIL: Unsafe or duplicate CHE source path")
            return 1

        if (
            type(size) is not int
            or size < 0
            or not isinstance(checksum, str)
            or len(checksum) != 64
            or any(c not in "0123456789abcdef" for c in checksum)
        ):
            print("FAIL: Invalid file metadata:", name)
            return 1

        expected[name] = (size, checksum)

    actual = {}

    for path in SOURCE.rglob("*"):
        if path.is_symlink():
            print("FAIL: Symbolic link in CHE source")
            return 1

        if not path.is_file():
            continue

        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue

        relative = path.relative_to(SOURCE).as_posix()
        actual[relative] = (
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    if set(expected) != set(actual):
        print("FAIL: CHE source file inventory differs")
        print("Missing files:", len(set(expected) - set(actual)))
        print("Unexpected files:", len(set(actual) - set(expected)))
        return 1

    for name in sorted(expected):
        if expected[name] != actual[name]:
            print("FAIL: CHE source checksum or size differs:", name)
            return 1

    print("PASS: All 36 CHE source files match the manifest")
    print("PASS: No unexpected non-generated CHE files")
    print("PASS: No symbolic links in CHE source")
    print("INSTALLATION NOT AUTHORIZED: Source validation only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
