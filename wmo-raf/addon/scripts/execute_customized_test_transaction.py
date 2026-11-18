#!/usr/bin/env python3
"""Test customization-preserving CHE installation in disposable workspaces.

Not a production installer. Does not touch the running CAP installation.
"""
import argparse
import hashlib
import json
import os
import runpy
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
    parser.add_argument("--fail-after", type=int, default=0)
    args = parser.parse_args()

    supplied = Path(args.workspace).expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("Missing or unsafe workspace")
    workspace = supplied.resolve()
    relative = workspace.relative_to(TEST_ROOT)
    if len(relative.parts) != 1 or not workspace.name.startswith("rollback-"):
        raise ValueError("Only dedicated rollback test workspaces are supported")

    cap = workspace / "capcomposer/src/capcomposer"
    if cap.is_symlink() or not cap.is_dir():
        raise ValueError("Missing or unsafe disposable CAP source")

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

    baseline_template = (
        TEST_ROOT / "rollback-zlsek921/capcomposer/src/capcomposer/"
        "config/templates/wagtailadmin/base.html"
    )
    combined_template = COMBINED / "config/templates/wagtailadmin/base.html"

    if any(
        path.is_symlink() or not path.is_file()
        for path in (baseline_template, combined_template)
    ):
        raise ValueError("Missing or unsafe branding reference")

    original_logo = extract_block(
        baseline_template.read_bytes().decode("utf-8")
    )[2]
    combined_logo = extract_block(
        combined_template.read_bytes().decode("utf-8")
    )[2]

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

    for name in BRANDING:
        source = COMBINED / safe_relative(name)
        if source.is_symlink() or not source.is_file():
            raise ValueError("Unsafe branding source")
        operations.append(("CREATE", cap / name, source.read_bytes()))

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
