#!/usr/bin/env python3
"""Resolve CAP installation paths without changing files.

Read-only. Resolution is not permission to install CHE.
"""

import argparse
import json
from pathlib import Path
import sys

CONFIGS = (
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
)


def resolve_target(value):
    supplied = value.expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("Missing or unsafe CAP project root")

    root = supplied.resolve()
    source_parts = ("capcomposer", "src", "capcomposer")

    current = root
    for part in source_parts:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ValueError("Missing or unsafe CAP source layout")

    cap_source = current

    for relative in CONFIGS:
        path = cap_source
        for component in Path(relative).parts:
            path = path / component
            if path.is_symlink():
                raise ValueError("Symbolic link in CAP configuration path")
        if not path.is_file():
            raise ValueError("Missing required CAP configuration: " + relative)

    journal = root / ".che-recovery-journal"
    if journal.exists() or journal.is_symlink():
        raise ValueError("Existing CHE recovery journal requires review")

    lock = root / ".che-transaction.lock"
    if lock.is_symlink():
        raise ValueError("Unsafe CHE transaction lock")

    if lock.exists() and not lock.is_file():
        raise ValueError("Unexpected CHE transaction lock type")

    che = cap_source / "che"
    if che.exists() or che.is_symlink():
        raise ValueError("Existing CHE destination requires review")

    return {
        "schema_version": 1,
        "cap_project_root": str(root),
        "cap_source_root": str(cap_source),
        "journal_path": str(journal),
        "lock_path": str(lock),
        "installation_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap-path", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = resolve_target(args.cap_path)
        print(json.dumps(result, indent=2))
        print("PASS: Portable CAP paths resolved", file=sys.stderr)
        print("READ ONLY: No installation authorized", file=sys.stderr)
        return 0
    except (OSError, ValueError) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
