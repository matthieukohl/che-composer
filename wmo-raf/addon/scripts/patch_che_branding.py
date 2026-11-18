#!/usr/bin/env python3
"""Preview a targeted CAP + CHE branding patch without modifying input files."""

import argparse
import difflib
import re
from pathlib import Path

START = re.compile(r"{%\s*block\s+branding_logo\s*%}")
END = re.compile(r"{%\s*endblock(?:\s+branding_logo)?\s*%}")


def extract_block(text):
    starts = list(START.finditer(text))
    if len(starts) != 1:
        raise ValueError("Missing or ambiguous branding_logo block")
    start = starts[0]
    endings = list(END.finditer(text, start.end()))
    if not endings:
        raise ValueError("Unclosed branding_logo block")
    end = endings[0]
    interior = text[start.end():end.start()]
    if re.search(r"{%\s*(?:block|endblock)\b", interior):
        raise ValueError("Nested branding blocks require manual review")
    return start.start(), end.end(), text[start.start():end.end()]


def patch_branding(text, original_block, combined_block):
    start, end, existing_block = extract_block(text)
    if existing_block == combined_block:
        return text
    if existing_block != original_block:
        raise ValueError(
            "Customized branding_logo block requires manual review; "
            "existing country branding will not be overwritten"
        )
    proposed = text[:start] + combined_block + text[end:]
    if extract_block(proposed)[2] != combined_block:
        raise ValueError("Generated branding block verification failed")
    return proposed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--original-template", type=Path, required=True)
    parser.add_argument("--combined-template", type=Path, required=True)
    args = parser.parse_args()

    existing = args.source.read_text()
    original_block = extract_block(args.original_template.read_text())[2]
    combined_block = extract_block(args.combined_template.read_text())[2]
    proposed = patch_branding(existing, original_block, combined_block)

    print("".join(difflib.unified_diff(
        existing.splitlines(keepends=True),
        proposed.splitlines(keepends=True),
        fromfile="existing/wagtailadmin/base.html",
        tofile="proposed/wagtailadmin/base.html",
    )) or "NO CHANGES: Joint branding already installed")
    print("PASS: Preview only; input template unchanged")


if __name__ == "__main__":
    main()
