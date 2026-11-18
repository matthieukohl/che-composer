#!/usr/bin/env python3
"""Read-only Docker Compose container identity validation for a CAP deployment."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def docker(args):
    result = subprocess.run(
        ["docker", *args],
        capture_output=True, text=True, check=False, timeout=60,
    )
    if result.returncode:
        raise ValueError("Docker inspection failed")
    return result.stdout


def validate(args):
    supplied = args.target.expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("Missing or unsafe project directory")
    target = supplied.resolve()

    for value in (args.project, args.app_service, args.db_service):
        if not NAME.fullmatch(value):
            raise ValueError("Unsafe Compose identifier")
    if args.app_service == args.db_service:
        raise ValueError("Application and database services must differ")

    output = docker([
        "ps", "-a", "--filter",
        "label=com.docker.compose.project=" + args.project,
        "--format", "{{.ID}}",
    ])
    ids = output.splitlines()
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Missing or duplicate project container identifiers")
    if any(not re.fullmatch(r"[0-9a-f]{12,64}", value) for value in ids):
        raise ValueError("Invalid Docker container identifier")

    containers = json.loads(docker(["inspect", *ids]))
    if not isinstance(containers, list) or len(containers) != len(ids):
        raise ValueError("Unexpected Docker inspection inventory")

    required = {args.app_service, args.db_service}
    matched = {}
    inspected_ids = set()

    for item in containers:
        if not isinstance(item, dict):
            raise ValueError("Invalid container inspection record")

        identifier = item.get("Id")
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[0-9a-f]{64}", identifier)
            or identifier in inspected_ids
            or not any(identifier.startswith(short) for short in ids)
        ):
            raise ValueError("Unexpected inspected container identity")
        inspected_ids.add(identifier)

        config = item.get("Config")
        state = item.get("State")
        if not isinstance(config, dict) or not isinstance(state, dict):
            raise ValueError("Invalid container configuration or state")

        labels = config.get("Labels")
        if not isinstance(labels, dict):
            raise ValueError("Missing Docker Compose labels")
        if labels.get("com.docker.compose.project") != args.project:
            raise ValueError("Container belongs to a different Docker project")

        working_dir = labels.get("com.docker.compose.project.working_dir")
        if (
            not isinstance(working_dir, str)
            or Path(working_dir).resolve() != target
        ):
            raise ValueError("Container belongs to a different project directory")

        service = labels.get("com.docker.compose.service")
        if not isinstance(service, str) or not NAME.fullmatch(service):
            raise ValueError("Invalid Compose service label")

        if service in required:
            if service in matched:
                raise ValueError("Duplicate selected service container: " + service)
            if state.get("Running") is not True:
                raise ValueError("Selected service is not running: " + service)
            matched[service] = identifier

    if set(matched) != required:
        raise ValueError("Required application or database service is missing")

    print("PASS: Compose project and working directory identities match")
    print("PASS: Application container running:", args.app_service)
    print("PASS: Database container running:", args.db_service)
    print("PASS: Selected container identities are unique")
    print("NOTE: PostgreSQL identity and Django database connection are separate checks")
    print("READ ONLY: No containers or databases modified")
    print("INSTALLATION NOT AUTHORIZED: Runtime identity check only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--app-service", required=True)
    parser.add_argument("--db-service", required=True)
    args = parser.parse_args()

    try:
        validate(args)
        return 0
    except (
        OSError, ValueError, TypeError, json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
