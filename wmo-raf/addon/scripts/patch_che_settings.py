#!/usr/bin/env python3
"""Generate minimal CHE settings additions without changing the input file."""

import argparse
import ast
import difflib
from pathlib import Path

APP = "capcomposer.che"
PROCESSOR = "capcomposer.config.branding.composer_branding"
APP_ANCHOR = "capcomposer.cap"
PROCESSOR_ANCHOR = "django.contrib.messages.context_processors.messages"


def find_list(tree, name):
    matches = [
        value
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in statement.targets)
        for value in [statement.value]
    ]
    if len(matches) != 1 or not isinstance(matches[0], ast.List):
        raise ValueError("Cannot uniquely identify " + name + " list")
    return matches[0]


def find_processors(tree):
    templates = find_list(tree, "TEMPLATES")
    matches = []
    for entry in templates.elts:
        if not isinstance(entry, ast.Dict):
            continue
        options = None
        backend = None
        for key, value in zip(entry.keys, entry.values):
            if isinstance(key, ast.Constant) and key.value == "BACKEND":
                backend = value.value if isinstance(value, ast.Constant) else None
            if isinstance(key, ast.Constant) and key.value == "OPTIONS":
                options = value
        if backend != "django.template.backends.django.DjangoTemplates":
            continue
        if not isinstance(options, ast.Dict):
            raise ValueError("Django template OPTIONS structure unsupported")
        for key, value in zip(options.keys, options.values):
            if isinstance(key, ast.Constant) and key.value == "context_processors":
                matches.append(value)
    if len(matches) != 1 or not isinstance(matches[0], ast.List):
        raise ValueError("Cannot uniquely identify Django context_processors list")
    return matches[0]


def addition(lines, node, value, anchor):
    entries = [
        entry for entry in node.elts
        if isinstance(entry, ast.Constant) and isinstance(entry.value, str)
    ]
    if len(entries) != len(node.elts):
        raise ValueError("Dynamic or unsupported list contents; manual review required")
    names = [entry.value for entry in entries]
    if names.count(value) > 1:
        raise ValueError("Duplicate CHE registration: " + value)
    if value in names:
        return None
    anchors = [entry for entry in entries if entry.value == anchor]
    if len(anchors) != 1:
        raise ValueError("Missing or ambiguous insertion anchor: " + anchor)
    entry = anchors[0]
    line = lines[entry.end_lineno - 1]
    indent = line[:len(line) - len(line.lstrip())]
    if not indent or not line.lstrip().startswith(('"', "'")):
        raise ValueError("Unrecognized list formatting near " + anchor)
    if not line.strip().split("#", 1)[0].rstrip().endswith(","):
        raise ValueError("Expected comma after " + anchor)
    newline = chr(13) + chr(10) if line.endswith(chr(13) + chr(10)) else chr(10)
    return entry.end_lineno, indent + '"' + value + '",' + newline


def patch_settings(text):
    tree = ast.parse(text)
    apps = find_list(tree, "INSTALLED_APPS")
    processors = find_processors(tree)
    lines = text.splitlines(keepends=True)
    changes = [
        addition(lines, apps, APP, APP_ANCHOR),
        addition(lines, processors, PROCESSOR, PROCESSOR_ANCHOR),
    ]
    for change in sorted((c for c in changes if c), reverse=True):
        index, insertion = change
        lines.insert(index, insertion)
    result = "".join(lines)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    original = args.source.read_text()
    patched = patch_settings(original)
    print("".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        patched.splitlines(keepends=True),
        fromfile="existing/base.py",
        tofile="proposed/base.py",
    )) or "NO CHANGES: CHE is already registered")
    print("PASS: Source file unchanged; patch generated in memory")


if __name__ == "__main__":
    main()
