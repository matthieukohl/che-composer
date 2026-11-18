#!/usr/bin/env python3
"""Read-only destination conflict checks for the isolated CHE add-on test."""
import argparse
from pathlib import Path
import sys

EXPECTED_TARGET = (
    Path(__file__).resolve().parent.parent / "test-cap-source"
).resolve()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Existing CAP Composer source")
    args = parser.parse_args()

    supplied = Path(args.target).expanduser()
    if supplied.is_symlink() or supplied.resolve() != EXPECTED_TARGET:
        print("FAIL: Target is not the isolated CAP-only test source")
        return 1

    root = EXPECTED_TARGET / "capcomposer/src/capcomposer"
    config = root / "config"

    new_destinations = {
        "CHE application": root / "che",
        "Branding context processor": config / "branding.py",
        "Combined branding image": config / "static/images/cap_che_composer.png",
    }

    existing_files = {
        "Django settings": config / "settings/base.py",
        "Django URL routing": config / "urls.py",
        "Wagtail admin template": config / "templates/wagtailadmin/base.html",
    }

    for label, path in new_destinations.items():
        if path.exists() or path.is_symlink():
            print("FAIL: Installation destination already occupied:", label)
            return 1
        print("PASS: Destination available:", label)

    for label, path in existing_files.items():
        if path.is_symlink() or not path.is_file():
            print("FAIL: Required CAP configuration file missing or unsafe:", label)
            return 1
        print("PASS: Existing file requires controlled modification:", label)

    for parent in (
        root,
        config,
        config / "settings",
        config / "static",
        config / "static/images",
        config / "templates",
        config / "templates/wagtailadmin",
    ):
        if parent.is_symlink() or not parent.is_dir():
            print("FAIL: Unsafe or missing installation parent:", parent)
            return 1

    print("PASS: No occupied CHE destinations identified")
    print("NOTE: This does not authorize overwriting existing CAP files")
    print("INSTALLATION NOT AUTHORIZED: Destination checks only")
    return 0

if __name__ == "__main__":
    sys.exit(main())
