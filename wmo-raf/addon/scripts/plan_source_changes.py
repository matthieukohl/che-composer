#!/usr/bin/env python3
"""Read-only plan for CHE integration into verified CAP Composer v1.3.6."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "wmo-raf/addon/integration/upstream_manifest.json"
COMBINED = ROOT / "wmo-raf/combined"

CHANGES = {
    "capcomposer/src/capcomposer/config/settings/base.py": [
        (
            '    "capcomposer.cap",\n',
            '    "capcomposer.cap",\n    "capcomposer.che",\n',
        ),
        (
            '                "django.contrib.messages.context_processors.messages",\n',
            '                "django.contrib.messages.context_processors.messages",\n'
            '                "capcomposer.config.branding.composer_branding",\n',
        ),
    ],
    "capcomposer/src/capcomposer/config/urls.py": [
        (
            '    path("documents/", include(wagtaildocs_urls)),\n',
            '    path("documents/", include(wagtaildocs_urls)),\n'
            '    path("che/", include("capcomposer.che.urls")),\n',
        ),
    ],
}

TEMPLATE = "capcomposer/src/capcomposer/config/templates/wagtailadmin/base.html"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    expected_target = (ROOT / "wmo-raf/addon/test-cap-source").resolve()

    if target != expected_target or not target.is_dir():
        print("FAIL: Only isolated CAP add-on test source is supported")
        return 1

    try:
        manifest = json.loads(MANIFEST.read_text())
        upstream_hashes = manifest["sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        print("FAIL: Cannot read upstream compatibility manifest")
        return 1

    proposals = {}

    for relative, replacements in CHANGES.items():
        source = target / relative
        expected = COMBINED / relative

        if source.is_symlink() or not source.is_file() or not expected.is_file():
            print("FAIL: Required source or reference missing:", relative)
            return 1

        original = source.read_bytes()
        if sha256(original) != upstream_hashes.get(relative):
            print("FAIL: Upstream source checksum mismatch:", relative)
            return 1

        content = original.decode("utf-8")
        for before, after in replacements:
            if content.count(before) != 1:
                print("FAIL: Unsafe or ambiguous insertion point:", relative)
                return 1
            content = content.replace(before, after, 1)

        proposal = content.encode("utf-8")
        if proposal != expected.read_bytes():
            print("FAIL: Proposed modification differs from combined release:", relative)
            return 1

        proposals[relative] = proposal

    original_template = target / TEMPLATE
    combined_template = COMBINED / TEMPLATE

    if (
        original_template.is_symlink()
        or not original_template.is_file()
        or not combined_template.is_file()
        or sha256(original_template.read_bytes()) != upstream_hashes.get(TEMPLATE)
    ):
        print("FAIL: Original Wagtail template cannot be verified")
        return 1

    proposals[TEMPLATE] = combined_template.read_bytes()

    for relative, content in sorted(proposals.items()):
        print("PASS: Proposed source change:", relative)
        print("  Proposed SHA-256:", sha256(content))

    print("PASS: All proposed changes match the combined release")
    print("DRY RUN ONLY: No source files modified")
    print("INSTALLATION NOT AUTHORIZED: Source-change planning only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
