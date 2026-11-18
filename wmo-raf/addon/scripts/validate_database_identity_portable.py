#!/usr/bin/env python3
"""Read-only PostgreSQL and Django database identity validation."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

DJANGO_QUERY = """
import django
import json
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_user")
    database, user = cursor.fetchone()
print(json.dumps({
    "database": database,
    "user": user,
    "host": connection.settings_dict.get("HOST", "")
}))
"""


def run(command, cwd):
    result = subprocess.run(
        command, cwd=str(cwd), capture_output=True,
        text=True, check=False, timeout=90,
    )
    if result.returncode:
        raise ValueError("Read-only Docker database inspection failed")
    return result.stdout.strip()


def verify(args):
    supplied = args.target.expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("Missing or unsafe CAP project root")
    target = supplied.resolve()

    for value in (
        args.db_user, args.database, args.django_db_user,
    ):
        if not NAME.fullmatch(value):
            raise ValueError("Unsafe PostgreSQL identifier")

    for value in (
        args.project, args.app_service, args.db_service,
        args.expected_db_host,
    ):
        if not PROJECT.fullmatch(value):
            raise ValueError("Unsafe Docker or database host identifier")

    if args.app_service == args.db_service:
        raise ValueError("Application and database services must differ")

    compose = ["docker", "compose", "-p", args.project]
    resolved = set()
    for relative in args.compose_file:
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe Compose file path")
        current = target
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic-link Compose file path")
        if not current.is_file():
            raise ValueError("Missing Compose file")
        path = current.resolve()
        if path in resolved:
            raise ValueError("Duplicate Compose file")
        resolved.add(path)
        compose.extend(["-f", str(path)])

    db_output = run(
        compose + [
            "exec", "-T", args.db_service,
            "psql", "-X", "-At", "-v", "ON_ERROR_STOP=1",
            "-U", args.db_user, "-d", args.database,
            "-c", "SELECT current_database() || '|' || current_user;",
        ],
        target,
    )
    if db_output != args.database + "|" + args.db_user:
        raise ValueError("PostgreSQL service database identity mismatch")

    app_output = run(
        compose + [
            "exec", "-T", args.app_service,
            "python", "-c", DJANGO_QUERY,
        ],
        target,
    )
    try:
        identity = json.loads(app_output)
    except ValueError:
        raise ValueError("Django identity response is not valid JSON")

    if not isinstance(identity, dict):
        raise ValueError("Invalid Django database identity")
    if identity.get("database") != args.database:
        raise ValueError("Django connects to a different database")
    if identity.get("user") != args.django_db_user:
        raise ValueError("Django connects with an unexpected database user")
    if identity.get("host") != args.expected_db_host:
        raise ValueError("Django uses an unexpected database host")

    print("PASS: PostgreSQL service database and user verified")
    print("PASS: Django connected database verified:", args.database)
    print("PASS: Django connected database user verified")
    print("PASS: Django configured database host verified")
    print("NOTE: Container identity and Compose configuration remain separate gates")
    print("NOTE: This does not establish full database backup restorability")
    print("READ ONLY: No database writes or container changes")
    print("INSTALLATION NOT AUTHORIZED: Database identity check only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--compose-file", type=Path, action="append",
                        required=True)
    parser.add_argument("--app-service", required=True)
    parser.add_argument("--db-service", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--django-db-user", required=True)
    parser.add_argument("--expected-db-host", required=True)
    args = parser.parse_args()

    try:
        verify(args)
        return 0
    except (
        OSError, ValueError, TypeError, subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
