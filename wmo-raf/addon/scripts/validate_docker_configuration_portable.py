#!/usr/bin/env python3
"""Read-only, deployment-specific Docker Compose configuration validation."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def check(args):
    supplied = args.target.expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("Missing or unsafe installation root")
    target = supplied.resolve()

    for value in (args.project, args.app_service, args.db_service):
        if not NAME.fullmatch(value):
            raise ValueError("Unsafe Docker project or service identifier")
    if args.app_service == args.db_service:
        raise ValueError("Application and database services must differ")

    files = []
    for supplied_file in args.compose_file:
        if supplied_file.is_absolute():
            raise ValueError("Compose files must be relative to installation root")
        if ".." in supplied_file.parts or not supplied_file.parts:
            raise ValueError("Unsafe Compose file path")
        current = target
        for part in supplied_file.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic-link Compose file path")
        if not current.is_file():
            raise ValueError("Compose file missing: " + str(supplied_file))
        resolved = current.resolve()
        try:
            resolved.relative_to(target)
        except ValueError:
            raise ValueError("Compose file outside installation root")
        if resolved in files:
            raise ValueError("Duplicate Compose file")
        files.append(resolved)

    command = ["docker", "compose", "-p", args.project]
    for path in files:
        command.extend(["-f", str(path)])
    command.extend(["config", "--format", "json"])

    result = subprocess.run(
        command, cwd=str(target), capture_output=True,
        text=True, check=False, timeout=120,
    )
    if result.returncode:
        raise ValueError("Docker Compose configuration could not be resolved")

    document = json.loads(result.stdout)
    if not isinstance(document, dict):
        raise ValueError("Invalid Compose configuration structure")
    if document.get("name") != args.project:
        raise ValueError("Resolved Docker project name differs")

    services = document.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("Missing Compose services")

    for label, name in (
        ("application", args.app_service),
        ("database", args.db_service),
    ):
        service = services.get(name)
        if not isinstance(service, dict):
            raise ValueError("Missing selected " + label + " service: " + name)
        if not service.get("image") and not service.get("build"):
            raise ValueError("Selected service has no image or build: " + name)
        print("PASS: Selected", label, "service exists:", name)

    print("PASS: Resolved Docker project identity:", args.project)
    print("PASS: Compose files verified:", len(files))
    print("PASS: Total declared services:", len(services))
    print("NOTE: This does not verify running containers or database identity")
    print("NOTE: Runtime configuration and secret handling need separate checks")
    print("DRY RUN ONLY: No Docker containers or databases modified")
    print("INSTALLATION NOT AUTHORIZED: Configuration validation only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--compose-file", required=True, type=Path,
                        action="append")
    parser.add_argument("--app-service", required=True)
    parser.add_argument("--db-service", required=True)
    args = parser.parse_args()
    try:
        check(args)
        return 0
    except (
        OSError, ValueError, TypeError, json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
