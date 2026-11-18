#!/usr/bin/env python3
"""Single entry point for disposable CHE add-on installation tests.

Development only. National production installation is NOT authorized.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
SCRIPTS = ADDON / "scripts"
TEST_ROOT = (ADDON / "transaction-tests").resolve()

ACTIONS = {
    "plan": "plan_packaged_install_transaction.py",
    "install": "execute_packaged_test_transaction.py",
    "recover": "recover_source_from_journal.py",
}


def main():
    parser = argparse.ArgumentParser(
        description="Disposable CHE add-on installation workflow"
    )
    parser.add_argument("action", choices=sorted(ACTIONS))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()

    supplied = args.workspace.expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        print("FAIL: Missing or unsafe test workspace")
        return 1

    workspace = supplied.resolve()
    try:
        relative = workspace.relative_to(TEST_ROOT)
    except ValueError:
        print("FAIL: Workspace outside disposable transaction tests")
        return 1

    if len(relative.parts) != 1 or not workspace.name.startswith("rollback-"):
        print("FAIL: Only dedicated rollback test workspaces are supported")
        return 1

    cap = workspace / "capcomposer/src/capcomposer"
    if cap.is_symlink() or not cap.is_dir():
        print("FAIL: Missing or unsafe CAP test source")
        return 1

    script = SCRIPTS / ACTIONS[args.action]
    if script.is_symlink() or not script.is_file():
        print("FAIL: Required workflow component missing")
        return 1

    print("=== CHE add-on:", args.action, "===", flush=True)
    print("Test workspace:", workspace, flush=True)

    if args.action == "install":
        journal = workspace / ".che-recovery-journal"
        if journal.exists() or journal.is_symlink():
            print("FAIL: Existing recovery journal requires review or recovery")
            return 1

    arguments = (
        [str(workspace)]
        if args.action == "plan"
        else ["--workspace", str(workspace)]
    )

    outcome = subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
    )

    if outcome.returncode:
        print("FAIL: CHE", args.action, "did not complete")
        print("INSTALLATION NOT AUTHORIZED")
        return outcome.returncode

    if args.action == "install":
        journal_file = workspace / ".che-recovery-journal/journal.json"
        if journal_file.is_symlink() or not journal_file.is_file():
            print("FAIL: Installation recovery journal missing")
            return 1

        report = json.loads(journal_file.read_text())
        records = report.get("operations")
        if not isinstance(records, list) or len(records) != 41:
            print("FAIL: Invalid installed operation journal")
            return 1

        import hashlib
        for record in records:
            relative_path = Path(record["path"])
            if relative_path.is_absolute() or ".." in relative_path.parts:
                print("FAIL: Invalid installed path")
                return 1
            destination = cap / relative_path
            if destination.is_symlink() or not destination.is_file():
                print("FAIL: Installed file missing or unsafe")
                return 1
            if hashlib.sha256(destination.read_bytes()).hexdigest() != record["proposed_sha256"]:
                print("FAIL: Installed file integrity mismatch")
                return 1

        print("PASS: All 41 installation outputs independently verified")

    print("PASS: CHE add-on test workflow:", args.action)
    print("TEST ONLY: National production installation not authorized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
