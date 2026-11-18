#!/usr/bin/env python3
"""Read-only source-change planner preserving national CAP customizations."""

import argparse
import ast
import difflib
import hashlib
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "wmo-raf/addon/scripts"
REFERENCE = ROOT / "wmo-raf/addon/integration/branding_blocks.json"

FILES = (
    "config/settings/base.py",
    "config/urls.py",
    "config/templates/wagtailadmin/base.html",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe file: " + str(path))
    return path.read_bytes()


def make_patchers():
    settings = runpy.run_path(str(SCRIPTS / "patch_che_settings.py"))
    urls = runpy.run_path(str(SCRIPTS / "patch_che_urls.py"))
    branding = runpy.run_path(str(SCRIPTS / "patch_che_branding.py"))

    data = json.loads(safe_read(REFERENCE).decode("utf-8"))
    if data.get("cap_composer_version") != "1.3.6":
        raise ValueError("Unsupported branding reference version")

    manifest_path = ROOT / "wmo-raf/addon/integration/upstream_manifest.json"
    manifest = json.loads(safe_read(manifest_path).decode("utf-8"))
    template = "capcomposer/src/capcomposer/" + FILES[2]

    if data.get("upstream_template_sha256") != manifest["sha256"][template]:
        raise ValueError("Branding reference does not match upstream manifest")

    old = data["original_branding_logo_block"]
    new = data["joint_branding_logo_block"]
    if not isinstance(old, str) or not isinstance(new, str) or old == new:
        raise ValueError("Invalid branding block reference")

    return (
        settings["patch_settings"],
        urls["patch_urls"],
        lambda text: branding["patch_branding"](text, old, new),
    )


def plan(target, preview=True):
    if target.is_symlink() or not target.is_dir():
        raise ValueError("Missing or unsafe CAP source directory")

    cap = target / "capcomposer/src/capcomposer"
    if any(
        parent.is_symlink()
        for parent in (target / "capcomposer", target / "capcomposer/src", cap)
    ) or not cap.is_dir():
        raise ValueError("Unsafe CAP source layout")

    patchers = make_patchers()
    proposed_files = []

    # Compute and validate all proposed changes before printing approval.
    for relative, patch in zip(FILES, patchers):
        path = cap / relative
        if any(
            parent.is_symlink()
            for parent in (
                path.parent,
                path.parent.parent,
                path.parent.parent.parent,
            )
        ):
            raise ValueError("Symbolic-link configuration parent: " + relative)

        original = safe_read(path)
        text = original.decode("utf-8")
        proposed = patch(text)

        if proposed == text:
            raise ValueError(
                "CHE already integrated or no modification needed: " + relative
            )
        if patch(proposed) != proposed:
            raise ValueError("Non-idempotent patch: " + relative)
        if relative.endswith(".py"):
            ast.parse(proposed)

        proposed_bytes = proposed.encode("utf-8")
        if path.read_bytes() != original:
            raise ValueError("Configuration changed during planning: " + relative)

        proposed_files.append(
            (relative, text, proposed, digest(original), digest(proposed_bytes))
        )

    for relative, text, proposed, old_hash, new_hash in proposed_files:
        print("PASS: Planned targeted change:", relative)
        print("  Original SHA-256:", old_hash)
        print("  Proposed SHA-256:", new_hash)
        if preview:
            print("".join(difflib.unified_diff(
                text.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile="existing/" + relative,
                tofile="proposed/" + relative,
            )), end="")

    print("PASS: All three targeted changes validated")
    print("DRY RUN ONLY: No CAP source files modified")
    print("INSTALLATION NOT AUTHORIZED: Planning only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path, help="CAP Composer project root")
    parser.add_argument("--no-diff", action="store_true")
    args = parser.parse_args()
    plan(args.target.expanduser().absolute(), not args.no_diff)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, UnicodeError) as exc:
        print("FAIL:", exc)
        sys.exit(1)
