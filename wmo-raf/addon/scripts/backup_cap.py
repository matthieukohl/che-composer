#!/usr/bin/env python3
"""Safety preflight for CHE add-on installation backups.

This initial version does not perform backups.
"""
import argparse
import pathlib
import subprocess
import sys

def is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Check backup paths before CHE add-on installation"
    )
    parser.add_argument("target", help="Existing CAP Composer installation")
    parser.add_argument("destination", help="External backup destination")
    args = parser.parse_args()

    target = pathlib.Path(args.target).expanduser().resolve()
    destination = pathlib.Path(args.destination).expanduser().resolve()

    errors = []

    if not target.is_dir():
        errors.append("CAP Composer target directory does not exist")

    if is_within(destination, target):
        errors.append("Backup destination is inside the CAP installation")

    if is_within(target, destination):
        errors.append("Backup destination contains the CAP installation")

    if destination == target:
        errors.append("Backup destination equals the CAP installation")

    if destination.exists() and not destination.is_dir():
        errors.append("Backup destination is not a directory")

    release_root = pathlib.Path(__file__).resolve().parents[3]
    if is_within(destination, release_root):
        errors.append("Backup destination is inside CHE release repository")

    if destination.exists():
        result = subprocess.run(
            ["git", "-C", str(destination),
             "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            check=False,
        )

        if result.returncode == 0:
            repository = pathlib.Path(
                result.stdout.strip()
            ).resolve()

            if is_within(destination, repository):
                relative = destination.relative_to(repository)
                ignored = subprocess.run(
                    ["git", "-C", str(repository),
                     "check-ignore", "-q", str(relative)],
                    check=False,
                )

                if ignored.returncode != 0:
                    errors.append(
                        "Backup destination is inside a Git repository "
                        "and is not ignored"
                    )
    print("CHE Add-on — backup safety preflight")
    print("Target:", target)
    print("Destination:", destination)

    if errors:
        for error in errors:
            print("FAIL:", error)
        print("RESULT: Backup location rejected")
        return 1

    print("RESULT: Preliminary backup path checks passed")
    print("NOTE: No backup has been created or verified")
    return 0

if __name__ == "__main__":
    sys.exit(main())
