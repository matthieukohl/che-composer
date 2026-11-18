#!/usr/bin/env python3
"""Apply CHE source changes ONLY to the isolated CAP-only test source.

Development-only installer; not suitable for production use.
Requires explicit --apply and mandatory preflight checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TEST_ROOT = (ADDON / "transaction-tests").resolve()
CHE_SOURCE = ROOT / "che-core"
COMBINED = ROOT / "wmo-raf/combined/capcomposer/src/capcomposer"

MODIFIED = (
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
)
BRANDING = (
    "config/branding.py",
    "config/static/images/cap_che_composer.png",
)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def safe_relative(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Invalid relative path")
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        raise ValueError("Unsafe relative path")
    return path

def atomic_write(destination, data, mode=None):
    fd, temporary = tempfile.mkstemp(prefix=".che-txn-", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            else:
                os.fchmod(stream.fileno(), 0o644)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(destination))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--recovery-manifest", required=True)
    parser.add_argument("--restoration-evidence", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    supplied = Path(args.workspace).expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("Missing or unsafe installation target")
    workspace = supplied.resolve()
    expected = (ADDON / "test-cap-source").resolve()
    if workspace != expected:
        raise ValueError("Only the isolated CAP-only test installation is supported")

    cap = workspace / "capcomposer/src/capcomposer"
    if cap.is_symlink() or not cap.is_dir():
        raise ValueError("Missing or unsafe disposable CAP source")

    manifest = json.loads(
        (ADDON / "integration/che_source_manifest.json").read_text()
    )
    upstream = json.loads(
        (ADDON / "integration/upstream_manifest.json").read_text()
    )["sha256"]

    operations = []
    for record in manifest["files"]:
        relative = safe_relative(record["path"])
        source = CHE_SOURCE / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError("Unsafe CHE source")
        content = source.read_bytes()
        if len(content) != record["size"] or digest(content) != record["sha256"]:
            raise ValueError("CHE source integrity mismatch")
        operations.append(("CREATE", cap / "che" / relative, content))

    if len(operations) != 36:
        raise ValueError("Expected exactly 36 CHE files")

    for name in BRANDING:
        source = COMBINED / safe_relative(name)
        if source.is_symlink() or not source.is_file():
            raise ValueError("Unsafe branding source")
        operations.append(("CREATE", cap / name, source.read_bytes()))

    for name in MODIFIED:
        destination = cap / safe_relative(name)
        source = COMBINED / name
        expected = upstream.get("capcomposer/src/capcomposer/" + name)
        if (
            destination.is_symlink() or not destination.is_file()
            or digest(destination.read_bytes()) != expected
            or source.is_symlink() or not source.is_file()
        ):
            raise ValueError("Unverified CAP modification source")
        operations.append(("MODIFY", destination, source.read_bytes()))

    if len(operations) != 41:
        raise ValueError("Unexpected transaction size")

    seen = set()
    for action, destination, _ in operations:
        destination.relative_to(cap)
        if destination in seen:
            raise ValueError("Duplicate destination")
        seen.add(destination)
        if destination.is_symlink() or (action == "CREATE" and destination.exists()):
            raise ValueError("Occupied or unsafe destination")
        for parent in destination.parents:
            if parent == workspace.parent:
                break
            if parent.is_symlink():
                raise ValueError("Symbolic-link parent")

    import subprocess

    preflight = subprocess.run([
        sys.executable,
        str(ADDON / "scripts/install_che.py"),
        str(workspace),
        "--recovery-manifest", args.recovery_manifest,
        "--restoration-evidence", args.restoration_evidence,
    ], check=False)

    if preflight.returncode != 0:
        raise ValueError("Mandatory installation preflight failed")

    if not args.apply:
        print("PASS: Isolated installation plan verified")
        print("DRY RUN ONLY: Pass --apply to execute source changes")
        return 0

    completed = []
    created_dirs = []
    try:
        for number, (action, destination, content) in enumerate(operations, 1):
            missing = []
            parent = destination.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                created_dirs.append(directory)

            previous = destination.read_bytes() if action == "MODIFY" else None
            previous_mode = (
                destination.stat().st_mode & 0o777
                if action == "MODIFY" else None
            )
            # Record rollback state before modifying the destination.
            completed.append((action, destination, previous, previous_mode))
            atomic_write(destination, content, previous_mode)
            if digest(destination.read_bytes()) != digest(content):
                raise RuntimeError("Post-write checksum mismatch")


        print("PASS: All 41 CHE source operations applied to isolated CAP test source")
        print("PASS: Installed file checksums verified")
        print("NOTE: Docker images and database migrations were not changed")
        return 0

    except Exception as exc:
        print("Transaction interrupted:", exc)
        rollback_errors = []
        for action, destination, previous, previous_mode in reversed(completed):
            try:
                if action == "CREATE":
                    if destination.exists():
                        destination.unlink()
                else:
                    atomic_write(destination, previous, previous_mode)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))

        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass

        if rollback_errors:
            print("FAIL: Rollback incomplete:", len(rollback_errors))
            return 1

        for name in MODIFIED:
            destination = cap / name
            expected = upstream["capcomposer/src/capcomposer/" + name]
            if digest(destination.read_bytes()) != expected:
                print("FAIL: CAP configuration not fully restored:", name)
                return 1

        if (cap / "che").exists() or any((cap / name).exists() for name in BRANDING):
            print("FAIL: Created files remain after rollback")
            return 1

        print("PASS: Rollback restored original CAP configuration")
        print("PASS: Newly created CHE and branding files removed")
        print("NOTE: Crash-safe recovery is not yet implemented")
        return 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
