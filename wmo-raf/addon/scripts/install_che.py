#!/usr/bin/env python3
"""CHE Composer add-on installer (initial dry-run version).

No installation or database changes are performed by this version.
"""
import argparse
import pathlib
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(
        description="CHE Composer add-on source installation preflight"
    )
    parser.add_argument("target", help="Existing CAP Composer source directory")
    parser.add_argument(
        "--recovery-manifest",
        required=True,
        help="Recovery manifest containing verified backup artifact references",
    )
    parser.add_argument(
        "--restoration-evidence",
        required=True,
        help="Evidence of an independently tested CAP database restoration",
    )
    args = parser.parse_args()

    target = pathlib.Path(args.target).expanduser().resolve()
    release_root = pathlib.Path(__file__).resolve().parents[3]

    compatibility = (
        pathlib.Path(__file__).resolve().parent
        / "check_compatibility.py"
    )

    result = subprocess.run(
        [sys.executable, str(compatibility), str(target)],
        check=False,
    )

    if result.returncode != 0:
        print("INSTALLATION BLOCKED: Compatibility checks failed")
        return 1

    validator = (
        pathlib.Path(__file__).resolve().parent
        / "validate_recovery.py"
    )

    recovery_result = subprocess.run(
        [
            sys.executable,
            str(validator),
            str(target),
            args.recovery_manifest,
        ],
        check=False,
    )

    if recovery_result.returncode != 0:
        print("INSTALLATION BLOCKED: Recovery manifest checks failed")
        return 1

    restoration_validator = (
        pathlib.Path(__file__).resolve().parent
        / "validate_restoration.py"
    )

    restoration_result = subprocess.run(
        [
            sys.executable,
            str(restoration_validator),
            args.recovery_manifest,
            args.restoration_evidence,
        ],
        check=False,
    )

    if restoration_result.returncode != 0:
        print("INSTALLATION BLOCKED: Restoration evidence checks failed")
        return 1

    configuration_validator = (
        pathlib.Path(__file__).resolve().parent
        / "validate_configuration.py"
    )

    configuration_result = subprocess.run(
        [
            sys.executable,
            str(configuration_validator),
            str(target),
        ],
        check=False,
    )

    if configuration_result.returncode != 0:
        print("INSTALLATION BLOCKED: Docker configuration checks failed")
        return 1

    runtime_validator = (
        pathlib.Path(__file__).resolve().parent
        / "validate_runtime.py"
    )

    runtime_result = subprocess.run(
        [
            sys.executable,
            str(runtime_validator),
        ],
        check=False,
    )

    if runtime_result.returncode != 0:
        print("INSTALLATION BLOCKED: Runtime identity checks failed")
        return 1

    source_validator = (
        pathlib.Path(__file__).resolve().parent
        / "validate_che_source.py"
    )

    source_result = subprocess.run(
        [
            sys.executable,
            str(source_validator),
        ],
        check=False,
    )

    if source_result.returncode != 0:
        print("INSTALLATION BLOCKED: CHE source integrity checks failed")
        return 1

    destination_checker = (
        pathlib.Path(__file__).resolve().parent
        / "check_destinations.py"
    )

    destination_result = subprocess.run(
        [
            sys.executable,
            str(destination_checker),
            str(target),
        ],
        check=False,
    )

    if destination_result.returncode != 0:
        print("INSTALLATION BLOCKED: Destination conflict checks failed")
        return 1

    transaction_planner = (
        pathlib.Path(__file__).resolve().parent
        / "plan_install_transaction.py"
    )

    transaction_result = subprocess.run(
        [
            sys.executable,
            str(transaction_planner),
        ],
        check=False,
    )

    if transaction_result.returncode != 0:
        print("INSTALLATION BLOCKED: Source transaction planning failed")
        return 1

    che_core = release_root / "che-core"
    combined_config = (
        release_root
        / "wmo-raf/combined/capcomposer/src/capcomposer/config"
    )

    required = [
        che_core / "apps.py",
        che_core / "models.py",
        che_core / "migrations/0001_initial.py",
        combined_config / "branding.py",
        combined_config / "static/images/cap_che_composer.png",
        combined_config / "templates/wagtailadmin/base.html",
    ]

    missing = [str(path) for path in required if not path.is_file()]

    if missing:
        for path in missing:
            print("MISSING:", path)
        return 1

    print()
    print("=== CHE Add-on installation plan ===")
    print("Target:", target)
    print("CHE source:", che_core)
    print()
    print("Planned operations:")
    print("1. Copy CHE source into capcomposer/src/capcomposer/che/")
    print("2. Register capcomposer.che in Django INSTALLED_APPS")
    print("3. Register /che/ URL routing")
    print("4. Install conditional CAP + CHE branding")
    print("5. Rebuild Docker application images")
    print("6. Apply CHE migrations under explicit control")
    print("7. Verify existing CAP records and CHE functionality")
    print()
    print("DRY RUN ONLY: No files or databases were modified")
    print("INSTALLATION NOT AUTHORIZED: Backup gate not implemented")
    return 0

if __name__ == "__main__":
    sys.exit(main())
