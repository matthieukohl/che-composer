#!/usr/bin/env python3
"""Test CHE installation using permanent release branding references.

Not a production installer. Does not touch the running CAP installation.
"""
import argparse
import hashlib
import json
import os
import fcntl
import stat
import runpy
import subprocess
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TEST_ROOT = (ADDON / "transaction-tests").resolve()
CHE_SOURCE = ROOT / "che-core"
BRANDING_ASSETS = ADDON / "integration/assets"
BRANDING_MANIFEST = ADDON / "integration/branding_assets_manifest.json"

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


def acquire_che_test_lock(workspace):
    """Advisory, exclusive lock retained until this process exits."""
    location = workspace / ".che-transaction.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    fd = os.open(str(location), flags, 0o600)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", "--cap-path", required=True)
    parser.add_argument("--fail-after", type=int, default=0)
    args = parser.parse_args()

    supplied = Path(args.workspace).expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("Missing or unsafe workspace")
    workspace = supplied.resolve()
    if not is_disposable_workspace(workspace):
        raise ValueError("Only dedicated rollback test workspaces are supported")

    che_transaction_lock_fd = acquire_che_test_lock(workspace)
    # Keep the descriptor alive throughout this operation.
    cap = workspace / "capcomposer/src/capcomposer"
    if cap.is_symlink() or not cap.is_dir():
        raise ValueError("Missing or unsafe disposable CAP source")


    # An existing journal may indicate interrupted installation.
    # Refuse to proceed even if CAP files still appear unmodified.
    existing_journal = workspace / ".che-recovery-journal"
    if existing_journal.exists() or existing_journal.is_symlink():
        raise ValueError(
            "Existing recovery journal requires recovery or review"
        )

    manifest = json.loads(
        (ADDON / "integration/che_source_manifest.json").read_text()
    )
    patch_settings = runpy.run_path(
        str(ADDON / "scripts/patch_che_settings.py")
    )["patch_settings"]
    patch_urls = runpy.run_path(
        str(ADDON / "scripts/patch_che_urls.py")
    )["patch_urls"]
    branding_module = runpy.run_path(
        str(ADDON / "scripts/patch_che_branding.py")
    )
    extract_block = branding_module["extract_block"]
    patch_branding = branding_module["patch_branding"]

    reference_path = ADDON / "integration/branding_blocks.json"
    manifest_path = ADDON / "integration/upstream_manifest.json"

    if any(
        path.is_symlink() or not path.is_file()
        for path in (reference_path, manifest_path)
    ):
        raise ValueError("Missing or unsafe branding reference")

    reference = json.loads(reference_path.read_text())
    upstream_manifest = json.loads(manifest_path.read_text())
    template_name = (
        "capcomposer/src/capcomposer/"
        "config/templates/wagtailadmin/base.html"
    )

    if (
        reference.get("cap_composer_version") != "1.3.6"
        or upstream_manifest.get("version") != "1.3.6"
        or reference.get("upstream_template_sha256")
        != upstream_manifest["sha256"][template_name]
    ):
        raise ValueError("Branding reference does not match CAP baseline")

    original_logo = reference["original_branding_logo_block"]
    combined_logo = reference["joint_branding_logo_block"]

    if (
        not isinstance(original_logo, str)
        or not isinstance(combined_logo, str)
        or original_logo == combined_logo
    ):
        raise ValueError("Invalid permanent branding reference")

    if (
        extract_block(original_logo)[2] != original_logo
        or extract_block(combined_logo)[2] != combined_logo
    ):
        raise ValueError("Malformed branding reference blocks")

    patchers = (
        patch_settings,
        patch_urls,
        lambda text: patch_branding(text, original_logo, combined_logo),
    )

    original_configs = {}
    original_modes = {}

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

    branding_manifest_path = BRANDING_MANIFEST
    if branding_manifest_path.is_symlink() or not branding_manifest_path.is_file():
        raise ValueError("Unsafe branding asset manifest")

    branding_manifest = json.loads(branding_manifest_path.read_text())
    if branding_manifest.get("cap_composer_version") != "1.3.6":
        raise ValueError("Unexpected branding manifest version")

    records = branding_manifest.get("assets")
    if not isinstance(records, list) or len(records) != len(BRANDING):
        raise ValueError("Unexpected branding asset inventory")

    packaged = {}
    for record in records:
        name = record["path"]
        relative = safe_relative(name)
        if name in packaged or name not in BRANDING:
            raise ValueError("Duplicate or unexpected branding asset")
        source = BRANDING_ASSETS / relative
        current = source
        while current != BRANDING_ASSETS:
            if current.is_symlink():
                raise ValueError("Symbolic-link branding asset path")
            current = current.parent
        if source.is_symlink() or not source.is_file():
            raise ValueError("Unsafe packaged branding source")
        content = source.read_bytes()
        if len(content) != record["size"] or digest(content) != record["sha256"]:
            raise ValueError("Packaged branding asset integrity mismatch")
        packaged[name] = content

    if set(packaged) != set(BRANDING):
        raise ValueError("Missing packaged branding asset")

    for name in BRANDING:
        operations.append(("CREATE", cap / name, packaged[name]))

    for name, patch in zip(MODIFIED, patchers):
        destination = cap / safe_relative(name)
        if destination.is_symlink() or not destination.is_file():
            raise ValueError("Missing or unsafe CAP configuration: " + name)

        previous = destination.read_bytes()
        mode = destination.stat().st_mode & 0o777
        try:
            text = previous.decode("utf-8")
            proposed = patch(text)
            content = proposed.encode("utf-8")
        except (UnicodeError, SyntaxError, ValueError) as exc:
            raise ValueError(
                "Unsafe or unsupported customization in " + name
            ) from exc

        if content == previous:
            raise ValueError(
                "CHE already registered or no patch needed: " + name
            )

        original_configs[name] = previous
        original_modes[name] = mode
        operations.append(("MODIFY", destination, content))

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

    if args.fail_after < 0 or args.fail_after > 41:
        raise ValueError("Invalid failure injection number")


    # A durable journal must exist before the first installation write.
    preparer = ADDON / "scripts/prepare_source_recovery_journal.py"
    if preparer.is_symlink() or not preparer.is_file():
        raise ValueError("Recovery journal preparer unavailable")

    # Installer already holds the workspace lock. Avoid a second lock
    # by preparing the journal within this same locked process.
    prepare_journal = runpy.run_path(str(preparer))["prepare"]
    prepare_journal(workspace)

    journal_dir = workspace / ".che-recovery-journal"
    journal_file = journal_dir / "journal.json"
    if journal_dir.is_symlink() or journal_file.is_symlink():
        raise ValueError("Unsafe published recovery journal")

    journal = json.loads(journal_file.read_text())
    records = journal.get("operations")
    if (
        journal.get("schema_version") != 1
        or journal.get("state") != "prepared"
        or journal.get("workspace") != str(workspace)
        or not isinstance(records, list)
        or len(records) != 41
    ):
        raise ValueError("Recovery journal identity mismatch")

    journal_map = {r["path"]: r for r in records}
    if len(journal_map) != 41:
        raise ValueError("Duplicate recovery journal operation")

    for action, destination, content in operations:
        name = destination.relative_to(cap).as_posix()
        record = journal_map.get(name)
        if (
            record is None
            or record.get("action") != action
            or record.get("proposed_sha256") != digest(content)
        ):
            raise ValueError("Recovery journal differs from installation plan")
        if action == "MODIFY":
            snapshot = journal_dir / record["snapshot"]
            if snapshot.is_symlink() or not snapshot.is_file():
                raise ValueError("Unsafe recovery snapshot")
            if (
                snapshot.read_bytes() != original_configs[name]
                or record.get("original_sha256") != digest(original_configs[name])
                or record.get("original_mode") != original_modes[name]
            ):
                raise ValueError("Recovery snapshot differs from source")

    print("PASS: Recovery journal prepared and matched to all 41 operations")

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

            if number == args.fail_after:
                raise RuntimeError("SIMULATED FAILURE after operation " + str(number))

        print("PASS: All 41 customized-safe operations installed in disposable workspace")
        print("PASS: Installed file checksums verified")
        print("TEST ONLY: No active CAP installation modified")
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
            if (
                destination.read_bytes() != original_configs[name]
                or (destination.stat().st_mode & 0o777)
                != original_modes[name]
            ):
                print("FAIL: National CAP configuration not fully restored:", name)
                return 1

        if (cap / "che").exists() or any((cap / name).exists() for name in BRANDING):
            print("FAIL: Created files remain after rollback")
            return 1

        print("PASS: Rollback restored original national CAP configuration")
        print("PASS: Newly created CHE and branding files removed")
        print("NOTE: Crash-safe recovery is not yet implemented")
        return 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
