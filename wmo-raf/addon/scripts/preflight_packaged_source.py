#!/usr/bin/env python3
"""Read-only portable CHE source preflight; NOT installation authorization."""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

CHECKS = (
    ("CAP Composer compatibility", "check_compatibility_customized.py"),
    ("Destination safety", "check_destinations_portable.py"),
    ("41-operation source plan", "plan_packaged_install_transaction.py"),
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path, help="CAP Composer project root")
    args = parser.parse_args()

    supplied = args.target.expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        print("FAIL: Missing or unsafe CAP Composer project root")
        return 1
    target = supplied.absolute()

    print("=== CHE packaged source preflight ===", flush=True)
    print("Target:", target, flush=True)

    for label, filename in CHECKS:
        script = SCRIPTS / filename
        if script.is_symlink() or not script.is_file():
            print("FAIL: Missing or unsafe checker:", filename)
            return 1

        print("\n=== " + label + " ===", flush=True)
        result = subprocess.run(
            [sys.executable, str(script), str(target)],
            check=False,
        )
        if result.returncode != 0:
            print("FAIL: Source preflight stopped at:", label, flush=True)
            print("INSTALLATION NOT AUTHORIZED", flush=True)
            return 1

    print("\nPASS: All packaged source preflight checks passed", flush=True)
    print("NOTE: National runtime compatibility is not established by these checks")
    print("NOTE: Verified backups, restoration, Docker/database identity and")
    print("      crash-safe recovery remain required before production installation")
    print("DRY RUN ONLY: No files or databases modified")
    print("INSTALLATION NOT AUTHORIZED: Source preflight only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
