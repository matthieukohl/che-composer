#!/usr/bin/env python3
"""Unified, read-only national CAP + CHE deployment preflight.

This performs checks only. It never installs CHE or authorizes installation.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def required_dict(obj, name, fields):
    value = obj.get(name)
    if not isinstance(value, dict):
        raise ValueError("Missing configuration section: " + name)
    if set(value) != set(fields):
        raise ValueError("Incorrect configuration keys in: " + name)
    for key in fields:
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError("Missing configuration value: " + name + "." + key)
    return value


def absolute_file(value, description):
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Unsafe or missing " + description)
    return path.resolve()


def check(config_path):
    if config_path.is_symlink() or not config_path.is_file():
        raise ValueError("Missing or unsafe deployment configuration")

    config = json.loads(config_path.read_text())
    if not isinstance(config, dict):
        raise ValueError("Invalid configuration structure")

    expected_sections = {
        "schema_version", "cap_path", "docker", "database", "recovery"
    }
    if set(config) != expected_sections or type(config["schema_version"]) is not int:
        raise ValueError("Unexpected deployment configuration fields")
    if config["schema_version"] != 1:
        raise ValueError("Unsupported deployment configuration version")

    cap = Path(config["cap_path"]).expanduser()
    if not cap.is_absolute() or cap.is_symlink() or not cap.is_dir():
        raise ValueError("Unsafe or missing national CAP project directory")
    cap = cap.resolve()

    docker = config["docker"]
    docker_fields = {"project", "app_service", "db_service", "compose_files"}
    if not isinstance(docker, dict) or set(docker) != docker_fields:
        raise ValueError("Invalid Docker configuration")
    for key in ("project", "app_service", "db_service"):
        if not isinstance(docker[key], str) or not NAME.fullmatch(docker[key]):
            raise ValueError("Unsafe Docker identifier: " + key)
    if docker["app_service"] == docker["db_service"]:
        raise ValueError("Application and database services must differ")

    compose_files = docker["compose_files"]
    if not isinstance(compose_files, list) or not compose_files:
        raise ValueError("At least one Compose file is required")

    compose_arguments = []
    seen = set()
    for item in compose_files:
        if not isinstance(item, str) or not item:
            raise ValueError("Invalid Compose filename")
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts or "\\" in item:
            raise ValueError("Unsafe Compose filename")
        current = cap
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic-link Compose path")
        if not current.is_file() or current.resolve() in seen:
            raise ValueError("Missing or duplicate Compose file")
        seen.add(current.resolve())
        compose_arguments.extend(["--compose-file", item])

    database = required_dict(
        config, "database",
        {
            "name", "db_user", "django_db_user",
            "host", "original_db", "restored_db"
        },
    )
    for key in ("name", "db_user", "django_db_user", "original_db", "restored_db"):
        if not IDENTIFIER.fullmatch(database[key]):
            raise ValueError("Unsafe database identifier: " + key)
    if not NAME.fullmatch(database["host"]):
        raise ValueError("Unsafe Django database host")
    if database["name"] != database["original_db"]:
        raise ValueError("Configured database and original database differ")
    if database["restored_db"] == database["original_db"]:
        raise ValueError("Original and restored databases must differ")
    if not database["restored_db"].startswith("che_restore_"):
        raise ValueError("Unexpected isolated restoration database name")

    recovery = required_dict(
        config, "recovery", {"manifest", "evidence", "container"}
    )
    if not NAME.fullmatch(recovery["container"]):
        raise ValueError("Unsafe PostgreSQL container identifier")
    manifest = absolute_file(recovery["manifest"], "recovery manifest")
    evidence = absolute_file(recovery["evidence"], "restoration evidence")

    common = [
        "--project", docker["project"],
        *compose_arguments,
        "--app-service", docker["app_service"],
        "--db-service", docker["db_service"],
    ]
    db_args = [
        "--db-user", database["db_user"],
        "--original-db", database["original_db"],
        "--restored-db", database["restored_db"],
    ]

    checks = [
        ("CAP source compatibility",
         "preflight_packaged_source.py", [str(cap)]),
        ("Docker Compose configuration",
         "validate_docker_configuration_portable.py",
         [str(cap), *common]),
        ("Running Docker service identity",
         "validate_docker_runtime_portable.py",
         [str(cap),
          "--project", docker["project"],
          "--app-service", docker["app_service"],
          "--db-service", docker["db_service"]]),
        ("Django and PostgreSQL database identity",
         "validate_database_identity_portable.py",
         [str(cap), *common,
          "--database", database["name"],
          "--db-user", database["db_user"],
          "--django-db-user", database["django_db_user"],
          "--expected-db-host", database["host"]]),
        ("Recovery manifest integrity",
         "validate_recovery_portable.py",
         [str(cap), str(manifest)]),
        ("PostgreSQL backup archive inspection",
         "verify_portable_database_archive.py",
         [str(cap), str(manifest),
          "--container", recovery["container"]]),
        ("Restoration evidence and comparisons",
         "verify_portable_restoration_evidence.py",
         [str(cap), str(manifest), str(evidence),
          "--container", recovery["container"], *db_args]),
    ]

    print("=== CHE national deployment preflight ===", flush=True)
    for label, filename, arguments in checks:
        checker = SCRIPTS / filename
        if checker.is_symlink() or not checker.is_file():
            raise ValueError("Missing checker: " + filename)

        print("CHECK:", label, flush=True)
        result = subprocess.run(
            [sys.executable, str(checker), *arguments],
            capture_output=True, text=True, check=False, timeout=360,
        )
        if result.returncode:
            raise ValueError("Failed check: " + label)
        print("PASS:", label, flush=True)

    print("PASS: All seven deployment preflight checks completed")
    print("NOTE: Each check establishes only its documented scope")
    print("NOTE: Restoration provenance and complete schema coverage remain limited")
    print("READ ONLY: No CHE installation or database modification")
    print("INSTALLATION NOT AUTHORIZED: Development preflight only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        check(args.config.expanduser())
        return 0
    except (
        OSError, ValueError, TypeError, KeyError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL:", exc)
        print("INSTALLATION NOT AUTHORIZED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
