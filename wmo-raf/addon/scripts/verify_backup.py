#!/usr/bin/env python3
"""Read-only verification of a CHE add-on PostgreSQL backup."""
import argparse
import hashlib
import pathlib
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", help="PostgreSQL custom-format backup")
    parser.add_argument("expected_sha256", help="Expected SHA-256 checksum")
    parser.add_argument(
        "--container",
        required=True,
        help="PostgreSQL container used for read-only archive inspection",
    )
    args = parser.parse_args()

    archive = pathlib.Path(args.archive).expanduser()

    if not archive.is_file() or archive.is_symlink():
        print("FAIL: Backup archive missing or unsafe")
        return 1

    if not (
        len(args.expected_sha256) == 64
        and all(c in "0123456789abcdef" for c in args.expected_sha256.lower())
    ):
        print("FAIL: Invalid SHA-256 checksum format")
        return 1

    actual = hashlib.sha256(archive.read_bytes()).hexdigest()

    if actual != args.expected_sha256.lower():
        print("FAIL: Backup checksum mismatch")
        return 1

    print("PASS: Backup SHA-256 checksum matches")

    cmd = [
        "docker", "exec", "-i",
        args.container,
        "pg_restore", "--list",
    ]

    with archive.open("rb") as backup:
        result = subprocess.run(
            cmd,
            stdin=backup,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )

    if result.returncode != 0:
        print("FAIL: PostgreSQL archive inspection failed")
        return 1

    print("PASS: PostgreSQL backup archive is readable")
    print("NOTE: Restoration verification is a separate requirement")
    return 0

if __name__ == "__main__":
    sys.exit(main())
