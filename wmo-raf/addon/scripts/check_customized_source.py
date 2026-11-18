#!/usr/bin/env python3
"""Read-only CHE integration compatibility check for three CAP configuration files."""

import argparse
import ast
import difflib
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "wmo-raf/addon/scripts"
BASELINE = ROOT / "wmo-raf/addon/transaction-tests/rollback-zlsek921/capcomposer/src/capcomposer"
COMBINED = ROOT / "wmo-raf/combined/capcomposer/src/capcomposer"

FILES = (
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
)


def check(cap, preview=False):
    if cap.is_symlink() or not cap.is_dir():
        raise ValueError("Missing or unsafe CAP source directory")

    settings = runpy.run_path(str(SCRIPTS / "patch_che_settings.py"))
    urls = runpy.run_path(str(SCRIPTS / "patch_che_urls.py"))
    branding = runpy.run_path(str(SCRIPTS / "patch_che_branding.py"))

    original_template = BASELINE / FILES[2]
    combined_template = COMBINED / FILES[2]
    if any(
        path.is_symlink() or not path.is_file()
        for path in (original_template, combined_template)
    ):
        raise ValueError("Missing or unsafe branding reference")

    original_logo = branding["extract_block"](original_template.read_text())[2]
    combined_logo = branding["extract_block"](combined_template.read_text())[2]

    patchers = (
        settings["patch_settings"],
        urls["patch_urls"],
        lambda text: branding["patch_branding"](
            text, original_logo, combined_logo
        ),
    )

    for name, patch in zip(FILES, patchers):
        path = cap / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or unsafe CAP configuration: " + name)

        original = path.read_bytes()
        text = original.decode("utf-8")
        proposed = patch(text)

        if proposed == text:
            raise ValueError(
                "CHE integration already present or no change required: " + name
            )

        if patch(proposed) != proposed:
            raise ValueError("Patch is not idempotent: " + name)

        if name.endswith(".py"):
            ast.parse(proposed)

        print("PASS: Compatible configuration:", name, flush=True)
        if preview:
            print("".join(difflib.unified_diff(
                text.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile="existing/" + name,
                tofile="proposed/" + name,
            )), end="")

        if path.read_bytes() != original:
            raise ValueError("Configuration changed during inspection: " + name)

    print("PASS: All three CHE integration patches are compatible")
    print("READ ONLY: No CAP configuration files modified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cap_source", type=Path)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    check(args.cap_source.expanduser().resolve(), args.preview)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, SyntaxError, UnicodeError) as exc:
        print("FAIL:", exc)
        raise SystemExit(1)
