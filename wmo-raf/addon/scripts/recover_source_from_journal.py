#!/usr/bin/env python3
"""Conservative, repeatable source recovery in disposable rollback workspaces.

Development only: journal authenticity and transaction integration are pending.
"""

import argparse
import hashlib
import json
import os
import fcntl
import stat
from pathlib import Path
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TEST_ROOT = (ADDON / "transaction-tests").resolve()
MODIFIED = {
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
}
ASSETS = {
    "config/branding.py",
    "config/static/images/cap_che_composer.png",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(base, relative):
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
    ):
        raise ValueError("Invalid operation path")
    path = Path(relative)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != relative
    ):
        raise ValueError("Unsafe operation path")
    result = base
    for part in path.parts:
        result = result / part
        if result.is_symlink():
            raise ValueError("Symbolic link in operation path")
    return result


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def expected_paths():
    manifest = ADDON / "integration/che_source_manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Unsafe CHE manifest")
    source = json.loads(manifest.read_text())
    che = {"che/" + r["path"] for r in source["files"]}
    if len(che) != 36:
        raise ValueError("Unexpected CHE inventory")
    return che | ASSETS



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



def verify_recovery_patch(name, original, current):
    """Check a saved original reproduces the installed CHE modification."""
    from runpy import run_path

    try:
        original_text = original.decode("utf-8")
        current_text = current.decode("utf-8")

        script_names = {
            "config/settings/base.py":
                ("patch_che_settings.py", "patch_settings"),
            "config/urls.py":
                ("patch_che_urls.py", "patch_urls"),
        }

        if name in script_names:
            filename, function = script_names[name]
            script = ADDON / "scripts" / filename
            if script.is_symlink() or not script.is_file():
                raise ValueError("Missing CHE patcher")
            proposed = run_path(str(script))[function](original_text)

        elif name == "config/templates/wagtailadmin/base.html":
            script = ADDON / "scripts/patch_che_branding.py"
            if script.is_symlink() or not script.is_file():
                raise ValueError("Missing branding patcher")
            module = run_path(str(script))
            extract = module["extract_block"]
            patcher = module["patch_branding"]
            reference_path = ADDON / "integration/branding_blocks.json"
            if reference_path.is_symlink() or not reference_path.is_file():
                raise ValueError("Missing packaged branding reference")
            reference = json.loads(reference_path.read_text())
            if (
                not isinstance(reference, dict)
                or reference.get("cap_composer_version") != "1.3.6"
                or not isinstance(reference.get("original_branding_logo_block"), str)
                or not isinstance(reference.get("joint_branding_logo_block"), str)
            ):
                raise ValueError("Invalid packaged branding reference")
            original_block = reference["original_branding_logo_block"]
            combined_block = reference["joint_branding_logo_block"]
            if original_block == combined_block:
                raise ValueError("Invalid packaged branding blocks")
            if extract(original_text)[2] != original_block:
                raise ValueError("Saved original branding block differs from CAP reference")
            if extract(current_text)[2] != combined_block:
                raise ValueError("Installed CHE branding block differs from reference")
            proposed = patcher(original_text, original_block, combined_block)

        else:
            raise ValueError("Unexpected modified configuration")

        if proposed != current_text:
            raise ValueError("Saved original does not reproduce installed file")

    except (UnicodeError, ValueError, SyntaxError) as exc:
        raise ValueError(
            "Recovery snapshot does not reproduce installed CHE patch: "
            + name
        ) from exc



def trusted_creation_hashes():
    """Verify packaged CREATE inventory and return its trusted hashes."""
    specs = (
        (
            ADDON / "integration/che_source_manifest.json",
            "files", "che/", ROOT / "che-core", 36,
        ),
        (
            ADDON / "integration/branding_assets_manifest.json",
            "assets", "", ADDON / "integration/assets", 2,
        ),
    )
    expected = expected_paths()
    hashes = {}

    for manifest_path, field, prefix, source_root, count in specs:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("Unsafe packaged creation manifest")
        document = json.loads(manifest_path.read_text())
        records = document[field]
        if not isinstance(records, list) or len(records) != count:
            raise ValueError("Incorrect packaged creation inventory")

        for item in records:
            if not isinstance(item, dict):
                raise ValueError("Malformed packaged creation entry")
            relative = item.get("path")
            checksum = item.get("sha256")
            size = item.get("size")
            if not isinstance(relative, str) or not isinstance(checksum, str):
                raise ValueError("Malformed packaged creation checksum")
            name = prefix + relative

            if name not in expected or name in hashes:
                raise ValueError("Unexpected packaged creation path")
            if len(checksum) != 64 or any(
                character not in "0123456789abcdef" for character in checksum
            ):
                raise ValueError("Invalid packaged creation checksum")

            packaged_file = safe_path(source_root, relative)
            if not packaged_file.is_file():
                raise ValueError("Missing packaged creation file")
            content = packaged_file.read_bytes()
            if type(size) is not int or len(content) != size:
                raise ValueError("Packaged creation file size mismatch")
            if sha(content) != checksum:
                raise ValueError("Packaged creation file checksum mismatch")
            hashes[name] = checksum

    if len(hashes) != 38 or set(hashes) != expected:
        raise ValueError("Incomplete packaged creation inventory")
    return hashes


def recover(workspace):
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("Unsafe workspace")
    workspace = workspace.resolve()
    if not is_disposable_workspace(workspace):
        raise ValueError("Only disposable rollback workspaces are allowed")

    che_transaction_lock_fd = acquire_che_test_lock(workspace)
    # Keep the descriptor alive throughout this operation.
    cap = workspace / "capcomposer/src/capcomposer"
    for directory in (
        workspace / "capcomposer",
        workspace / "capcomposer/src",
        cap,
    ):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Unsafe CAP directory")

    journal = workspace / ".che-recovery-journal"
    if journal.is_symlink() or not journal.is_dir():
        raise ValueError("Missing or unsafe journal")

    manifest = journal / "journal.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Missing or unsafe journal manifest")
    data = json.loads(manifest.read_text())
    if (
        type(data) is not dict
        or data.get("schema_version") != 1
        or data.get("state") != "prepared"
        or data.get("workspace") != str(workspace)
    ):
        raise ValueError("Unexpected journal identity or state")

    records = data.get("operations")
    if not isinstance(records, list) or len(records) != 41:
        raise ValueError("Invalid operation inventory")

    creation_hashes = trusted_creation_hashes()
    changes = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Malformed operation record")
        name = record.get("path")
        if name in seen:
            raise ValueError("Duplicate journal path")
        seen.add(name)

        operation = record.get("action")
        if operation == "MODIFY":
            if name not in MODIFIED:
                raise ValueError("Unexpected modification path")
        elif operation == "CREATE":
            if name not in expected_paths():
                raise ValueError("Unexpected creation path")
        else:
            raise ValueError("Unknown journal operation")

        destination = safe_path(cap, name)
        proposed = record.get("proposed_sha256")
        if not (
            isinstance(proposed, str)
            and len(proposed) == 64
            and all(c in "0123456789abcdef" for c in proposed)
        ):
            raise ValueError("Invalid proposed checksum")

        if operation == "CREATE" and proposed != creation_hashes[name]:
            raise ValueError(
                "Recovery CREATE checksum differs from packaged release"
            )
        if operation == "MODIFY":
            snapshot_name = record.get("snapshot")
            if not (
                isinstance(snapshot_name, str)
                and snapshot_name.startswith("original-")
                and snapshot_name.endswith(".bin")
            ):
                raise ValueError("Unexpected snapshot name")
            snapshot = safe_path(journal, snapshot_name)
            if not snapshot.is_file():
                raise ValueError("Missing configuration snapshot")

            original = snapshot.read_bytes()
            if sha(original) != record.get("original_sha256"):
                raise ValueError("Damaged configuration snapshot")
            if sha(original) == proposed:
                raise ValueError("Recovery original and proposed checksums are identical")

            mode = record.get("original_mode")
            if type(mode) is not int or not (0 <= mode <= 0o777):
                raise ValueError("Invalid original permissions")

            if not destination.is_file():
                raise ValueError("Missing configuration file")
            current = destination.read_bytes()
            current_hash = sha(current)
            if current_hash not in (sha(original), proposed):
                raise ValueError("Unexpected change to configuration: " + name)
            if current_hash == proposed:
                verify_recovery_patch(name, original, current)
            changes.append((operation, destination, original, mode))
        else:
            if destination.exists():
                if not destination.is_file():
                    raise ValueError("Unexpected created-file type")
                if sha(destination.read_bytes()) != proposed:
                    raise ValueError("Unexpected change to created file: " + name)
            changes.append((operation, destination, None, None))

    if seen != MODIFIED | expected_paths():
        raise ValueError("Incomplete or altered journal inventory")

    # All paths are validated before making any changes. Unexpected files
    # block recovery, preventing deletion of national modifications.
    restored = 0
    removed = 0

    for operation, destination, original, mode in changes:
        if operation == "CREATE":
            if destination.exists():
                destination.unlink()
                fsync_dir(destination.parent)
                removed += 1
            continue

        if destination.read_bytes() == original:
            if stat.S_IMODE(destination.stat().st_mode) != mode:
                os.chmod(destination, mode)
            continue

        fd, temporary = tempfile.mkstemp(
            prefix=".che-recover-", dir=str(destination.parent)
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, destination)
            fsync_dir(destination.parent)
            restored += 1
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    print("PASS: Source recovery completed")
    print("PASS: Original configuration files restored:", restored)
    print("PASS: Unmodified CHE-created files removed:", removed)
    print("PASS: Recovery journal retained for inspection")
    print("NOTE: Journal authenticity and interrupted-recovery testing remain pending")
    print("TEST ONLY: Not authorized for operational deployments")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", "--cap-path", type=Path, required=True)
    args = parser.parse_args()
    try:
        recover(args.workspace.expanduser())
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
