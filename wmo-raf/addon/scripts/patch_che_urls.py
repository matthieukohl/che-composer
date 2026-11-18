#!/usr/bin/env python3
"""Preview minimal CHE URL integration without modifying existing CAP files."""

import argparse
import ast
import difflib
from pathlib import Path

CHE_TARGET = "capcomposer.che.urls"
CHE_LINE = 'path("che/", include("capcomposer.che.urls")),'


def route_details(node):
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Name) or node.func.id not in ("path", "re_path"):
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    route = node.args[0].value
    if not isinstance(route, str):
        return None
    return node.func.id, route, node


def is_che_include(node):
    if len(node.args) < 2:
        return False
    call = node.args[1]
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "include"
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == CHE_TARGET
    )


def patch_urls(text):
    tree = ast.parse(text)

    initial = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "urlpatterns"
            for target in node.targets
        )
        and isinstance(node.value, ast.List)
    ]
    if len(initial) != 1:
        raise ValueError("Cannot uniquely identify initial urlpatterns list")

    entries = initial[0].elts
    routes = [route_details(entry) for entry in entries]
    if any(route is None for route in routes):
        raise ValueError("Unsupported initial URL pattern; manual review required")

    # Inspect literal registrations throughout the file, including later additions.
    all_routes = [
        route_details(node)
        for node in ast.walk(tree)
        if route_details(node) is not None
    ]
    che_routes = [
        route for route in all_routes
        if route[1] == "che/" or route[1].startswith("che/")
        or (route[0] == "re_path" and route[1].startswith("^che/"))
    ]

    if che_routes:
        exact = [
            route for route in che_routes
            if route[0] == "path"
            and route[1] == "che/"
            and is_che_include(route[2])
        ]
        if len(che_routes) == 1 and len(exact) == 1:
            return text
        raise ValueError("Conflicting or ambiguous CHE route")

    anchors = [
        route[2] for route in routes
        if route[0] == "path" and route[1] == "documents/"
    ]
    if len(anchors) != 1:
        raise ValueError("Cannot identify documents/ insertion anchor")

    anchor = anchors[0]
    if anchor.lineno != anchor.end_lineno:
        raise ValueError("Multiline insertion anchor requires manual review")

    lines = text.splitlines(keepends=True)
    line = lines[anchor.end_lineno - 1]
    if not line.strip().endswith(","):
        raise ValueError("Unexpected route formatting")

    indent = line[:len(line) - len(line.lstrip())]
    if not indent:
        raise ValueError("Unexpected route indentation")

    newline = chr(13) + chr(10) if line.endswith(chr(13) + chr(10)) else chr(10)
    lines.insert(anchor.end_lineno, indent + CHE_LINE + newline)
    proposed = "".join(lines)
    ast.parse(proposed)
    return proposed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    original = args.source.read_text()
    proposed = patch_urls(original)
    print("".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        proposed.splitlines(keepends=True),
        fromfile="existing/urls.py",
        tofile="proposed/urls.py",
    )) or "NO CHANGES: CHE route already registered")
    print("PASS: Preview only; source unchanged")


if __name__ == "__main__":
    main()
