#!/usr/bin/env python3
"""Failure-injection test for a CHE source-file rollback.

Writes only inside a newly created disposable temporary directory.
Does not install CHE or change the active CAP Composer source.
"""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[3]
ADDON = ROOT / "wmo-raf/addon"
TEST_ROOT = ADDON / "transaction-tests"
BASELINE = TEST_ROOT / "rollback-zlsek921"
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


def main():
    baseline_cap = BASELINE / "capcomposer/src/capcomposer"
    manifest_path = ADDON / "integration/che_source_manifest.json"

    if BASELINE.is_symlink() or not baseline_cap.is_dir():
        raise RuntimeError("Disposable baseline workspace unavailable")

    manifest = json.loads(manifest_path.read_text())
    records = manifest["files"]

    if len(records) != 36:
        raise RuntimeError("Unexpected CHE source inventory")

    operations = []

    for record in records:
        name = record["path"]
        relative = Path(name)

        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or relative.as_posix() != name
        ):
            raise RuntimeError("Unsafe CHE path")

        source = CHE_SOURCE / relative

        if source.is_symlink() or not source.is_file():
            raise RuntimeError("Unsafe CHE source")

        content = source.read_bytes()

        if (
            len(content) != record["size"]
            or digest(content) != record["sha256"]
        ):
            raise RuntimeError("CHE source integrity mismatch")

        operations.append(("CREATE", Path("che") / relative, content))

    for name in BRANDING:
        source = COMBINED / name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("Unsafe branding source")
        operations.append(("CREATE", Path(name), source.read_bytes()))

    for name in MODIFIED:
        original = baseline_cap / name
        source = COMBINED / name

        if (
            original.is_symlink()
            or not original.is_file()
            or source.is_symlink()
            or not source.is_file()
        ):
            raise RuntimeError("Unsafe CAP configuration")

        operations.append(("MODIFY", Path(name), source.read_bytes()))

    if len(operations) != 41:
        raise RuntimeError("Unexpected transaction size")

    original_hashes = {
        name: digest((baseline_cap / name).read_bytes())
        for name in MODIFIED
    }

    with tempfile.TemporaryDirectory(
        prefix="rollback-simulation-",
        dir=str(TEST_ROOT),
    ) as temporary:
        test_cap = Path(temporary) / "capcomposer/src/capcomposer"
        shutil.copytree(str(baseline_cap), str(test_cap), symlinks=True)

        completed = []
        created_directories = []

        try:
            for number, (action, relative, content) in enumerate(
                operations, 1
            ):
                destination = test_cap / relative

                if destination.is_symlink():
                    raise RuntimeError("Unsafe destination")

                missing_parents = []
                parent = destination.parent

                while not parent.exists():
                    missing_parents.append(parent)
                    parent = parent.parent

                for directory in reversed(missing_parents):
                    directory.mkdir()
                    created_directories.append(directory)

                if action == "CREATE":
                    if destination.exists():
                        raise RuntimeError("Destination already occupied")
                    previous = None
                else:
                    if not destination.is_file():
                        raise RuntimeError("Existing CAP file missing")
                    previous = destination.read_bytes()

                with destination.open("wb") as stream:
                    stream.write(content)

                completed.append((action, destination, previous))

                if number == 40:
                    raise RuntimeError("SIMULATED FAILURE after operation 40")

        except RuntimeError as exc:
            if str(exc) != "SIMULATED FAILURE after operation 40":
                raise

            print("PASS: Injected failure after 40 operations")

            for action, destination, previous in reversed(completed):
                if action == "CREATE":
                    destination.unlink()
                else:
                    destination.write_bytes(previous)

            for directory in reversed(created_directories):
                directory.rmdir()

        else:
            raise RuntimeError("Failure injection did not occur")

        for name, expected_hash in original_hashes.items():
            actual = digest((test_cap / name).read_bytes())
            if actual != expected_hash:
                raise RuntimeError("CAP configuration rollback mismatch")
            print("PASS: Original configuration restored:", name)

        if (test_cap / "che").exists():
            raise RuntimeError("CHE directory remains after rollback")

        for name in BRANDING:
            if (test_cap / name).exists():
                raise RuntimeError("Branding file remains after rollback")

        print("PASS: Newly created CHE files removed")
        print("PASS: Simulated transaction rollback completed")
        print("NOTE: This tests ordinary failure handling, not power-loss recovery")

    print("PASS: Temporary simulation workspace removed")
    print("TEST ONLY: Active CAP installation was not modified")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
