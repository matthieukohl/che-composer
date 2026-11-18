#!/usr/bin/env python3
"""Read-only portable destination and source-layout checks for CHE."""

import argparse
import sys
from pathlib import Path

NEW = (
    "che",
    "config/branding.py",
    "config/static/images/cap_che_composer.png",
)
MODIFIED = (
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
)


def check(target):
    if target.is_symlink() or not target.is_dir():
        raise ValueError("Missing or unsafe CAP Composer project root")

    cap = target / "capcomposer/src/capcomposer"

    for path in (
        target / "capcomposer",
        target / "capcomposer/src",
        cap,
    ):
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Unsafe or missing CAP source directory: " + str(path))

    for name in NEW + MODIFIED:
        destination = cap / name
        current = destination
        while current != cap:
            if current.is_symlink():
                raise ValueError("Symbolic-link destination or parent: " + name)
            current = current.parent

    for name in NEW:
        destination = cap / name
        if destination.exists() or destination.is_symlink():
            raise ValueError("Occupied CHE destination: " + name)
        print("PASS: Destination available:", name)

    for name in MODIFIED:
        destination = cap / name
        if not destination.is_file() or destination.is_symlink():
            raise ValueError("Missing or unsafe CAP configuration: " + name)
        print("PASS: Existing configuration available:", name)

    print("PASS: Portable destination safety checks passed")
    print("DRY RUN ONLY: No installation files modified")
    print("INSTALLATION NOT AUTHORIZED: Destination checks only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path, help="CAP Composer project root")
    args = parser.parse_args()
    check(args.target.expanduser().absolute())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
