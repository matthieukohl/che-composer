#!/usr/bin/env python3
"""Prepare a durable 41-operation recovery journal in a disposable workspace.

Development-only. Does not install CHE or recover files.
"""

import argparse
import hashlib
import json
import os
import fcntl
import stat
from pathlib import Path
import runpy
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TEST_ROOT = (ADDON / "transaction-tests").resolve()
JOURNAL_NAME = ".che-recovery-journal"

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


def read_safe(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe source: " + str(path))
    return path.read_bytes()


def relative_path(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Invalid relative path")
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        raise ValueError("Unsafe relative path")
    return path


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)



def is_disposable_workspace(workspace):
    """Permit only controlled development fixtures, never a live CAP deployment."""
    try:
        relative = workspace.relative_to(TEST_ROOT)
    except ValueError:
        return False

    if len(relative.parts) == 1:
        return relative.parts[0].startswith("rollback-")

    return (
        len(relative.parts) == 2
        and relative.parts[0].startswith("portable-target-")
        and relative.parts[1] == "national-cap-project"
        and not workspace.parent.is_symlink()
    )


def prepare(workspace):
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("Missing or unsafe workspace")
    workspace = workspace.resolve()
    if not is_disposable_workspace(workspace):
        raise ValueError("Only disposable rollback workspaces are supported")

    cap = workspace / "capcomposer/src/capcomposer"
    for directory in (
        workspace / "capcomposer",
        workspace / "capcomposer/src",
        cap,
    ):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Unsafe CAP source layout")

    journal = workspace / JOURNAL_NAME
    if journal.exists() or journal.is_symlink():
        raise ValueError("Recovery journal already exists")

    planner = ADDON / "scripts/plan_packaged_install_transaction.py"
    import subprocess
    result = subprocess.run(
        [sys.executable, str(planner), str(workspace)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError("41-operation source plan failed")

    settings = runpy.run_path(str(ADDON / "scripts/patch_che_settings.py"))
    urls = runpy.run_path(str(ADDON / "scripts/patch_che_urls.py"))
    branding = runpy.run_path(str(ADDON / "scripts/patch_che_branding.py"))
    reference = json.loads(read_safe(ADDON / "integration/branding_blocks.json"))
    patchers = (
        settings["patch_settings"],
        urls["patch_urls"],
        lambda text: branding["patch_branding"](
            text,
            reference["original_branding_logo_block"],
            reference["joint_branding_logo_block"],
        ),
    )

    records = []
    snapshots = {}
    originals = {}

    for index, (name, patch) in enumerate(zip(MODIFIED, patchers)):
        path = cap / name
        data = read_safe(path)
        mode = path.stat().st_mode & 0o777
        after = patch(data.decode("utf-8")).encode("utf-8")
        if data == after:
            raise ValueError("No configuration patch required: " + name)
        snapshot = "original-" + str(index) + ".bin"
        originals[name] = data
        snapshots[snapshot] = data
        records.append({
            "action": "MODIFY",
            "path": name,
            "original_sha256": digest(data),
            "proposed_sha256": digest(after),
            "original_mode": mode,
            "snapshot": snapshot,
        })

    che_manifest = json.loads(
        read_safe(ADDON / "integration/che_source_manifest.json")
    )
    if len(che_manifest["files"]) != 36:
        raise ValueError("Unexpected CHE source count")
    for item in che_manifest["files"]:
        relative = relative_path(item["path"])
        data = read_safe(ROOT / "che-core" / relative)
        if len(data) != item["size"] or digest(data) != item["sha256"]:
            raise ValueError("CHE source checksum mismatch")
        records.append({
            "action": "CREATE",
            "path": "che/" + relative.as_posix(),
            "proposed_sha256": digest(data),
        })

    assets_manifest = json.loads(
        read_safe(ADDON / "integration/branding_assets_manifest.json")
    )
    assets = assets_manifest["assets"]
    if len(assets) != 2 or {r["path"] for r in assets} != set(BRANDING):
        raise ValueError("Unexpected branding inventory")
    for item in assets:
        relative = relative_path(item["path"])
        data = read_safe(ADDON / "integration/assets" / relative)
        if len(data) != item["size"] or digest(data) != item["sha256"]:
            raise ValueError("Branding source checksum mismatch")
        records.append({
            "action": "CREATE",
            "path": relative.as_posix(),
            "proposed_sha256": digest(data),
        })

    if len(records) != 41 or len({r["path"] for r in records}) != 41:
        raise ValueError("Invalid recovery operation inventory")

    for record in records:
        target = cap / relative_path(record["path"])
        current = target
        while current != cap:
            if current.is_symlink():
                raise ValueError("Symbolic-link operation destination")
            current = current.parent
        if record["action"] == "CREATE" and target.exists():
            raise ValueError("Occupied creation destination")
        if record["action"] == "MODIFY" and read_safe(target) != originals[record["path"]]:
            raise ValueError("Configuration changed during preparation")

    payload = {
        "schema_version": 1,
        "state": "prepared",
        "workspace": str(workspace),
        "operations": records,
    }

    # Journal is constructed out of sight, synced, then published by rename.
    staging = Path(tempfile.mkdtemp(prefix=".che-journal-staging-", dir=workspace))
    try:
        for name, data in snapshots.items():
            path = staging / name
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())

        manifest = staging / "journal.json"
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        sync_directory(staging)

        for name, original in originals.items():
            if read_safe(cap / name) != original:
                raise ValueError("CAP configuration changed before journal publication")
        if journal.exists() or journal.is_symlink():
            raise ValueError("Journal destination became occupied")

        staging.rename(journal)
        sync_directory(workspace)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    print("PASS: Durable recovery journal prepared")
    print("PASS: Three original configuration snapshots recorded")
    print("PASS: 41 expected operations and checksums recorded")
    print("PASS: Original file permissions recorded")
    print("NOTE: Recovery executor and process-crash simulation still required")
    print("TEST ONLY: No CHE files installed or CAP configurations changed")



def acquire_che_test_lock(workspace):
    """Standalone preparer lock; installer already owns its lock."""
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("Unsafe workspace")
    workspace = workspace.resolve()
    if not is_disposable_workspace(workspace):
        raise ValueError("Only disposable rollback workspaces are supported")

    location = workspace / ".che-transaction.lock"
    fd = os.open(str(location), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        information = os.fstat(fd)
        if (
            not stat.S_ISREG(information.st_mode)
            or information.st_uid != os.getuid()
            or information.st_nlink != 1
            or stat.S_IMODE(information.st_mode) != 0o600
        ):
            raise ValueError("Unsafe transaction lock file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            raise ValueError("Another CHE transaction holds the lock")
        return fd
    except BaseException:
        os.close(fd)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", "--cap-path", required=True, type=Path)
    args = parser.parse_args()
    try:
        workspace = args.workspace.expanduser()
        lock_fd = acquire_che_test_lock(workspace)
        try:
            prepare(workspace)
        finally:
            os.close(lock_fd)
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
