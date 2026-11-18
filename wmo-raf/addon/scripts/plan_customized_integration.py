#!/usr/bin/env python3
"""Read-only plan for customization-preserving CHE integration."""

import hashlib
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "wmo-raf/addon/scripts"
BASELINE = ROOT / "wmo-raf/addon/transaction-tests/rollback-zlsek921/capcomposer/src/capcomposer"
COMBINED = ROOT / "wmo-raf/combined/capcomposer/src/capcomposer"
INSTALLED = ROOT / "wmo-raf/addon/test-cap-source/capcomposer/src/capcomposer"

FILES = (
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
)


def load_patchers():
    settings = runpy.run_path(str(SCRIPTS / "patch_che_settings.py"))
    urls = runpy.run_path(str(SCRIPTS / "patch_che_urls.py"))
    branding = runpy.run_path(str(SCRIPTS / "patch_che_branding.py"))
    return settings["patch_settings"], urls["patch_urls"], branding


def verify_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe reference: " + str(path))
    return path.read_text()


def main():
    settings_patch, urls_patch, branding = load_patchers()

    original_logo = branding["extract_block"](
        verify_file(BASELINE / FILES[2])
    )[2]
    combined_logo = branding["extract_block"](
        verify_file(COMBINED / FILES[2])
    )[2]

    patchers = (
        settings_patch,
        urls_patch,
        lambda text: branding["patch_branding"](
            text, original_logo, combined_logo
        ),
    )

    for relative, patch in zip(FILES, patchers):
        original = verify_file(BASELINE / relative)
        expected = verify_file(COMBINED / relative)
        installed = verify_file(INSTALLED / relative)

        before_hash = hashlib.sha256(original.encode()).hexdigest()
        proposed = patch(original)

        if proposed != expected:
            raise ValueError("Patch differs from verified release: " + relative)
        if installed != expected:
            raise ValueError("Installed reference differs: " + relative)
        if patch(proposed) != proposed:
            raise ValueError("Patch is not idempotent: " + relative)
        if hashlib.sha256(
            (BASELINE / relative).read_bytes()
        ).hexdigest() != before_hash:
            raise ValueError("Baseline changed: " + relative)

        print("PASS: Verified minimal patch:", relative)

    print("PASS: All three patches reproduce the working combined release")
    print("PASS: All three patches are idempotent")
    print("PASS: Already-installed reference requires no further changes")
    print("READ ONLY: No installation files, containers or databases modified")


if __name__ == "__main__":
    main()
