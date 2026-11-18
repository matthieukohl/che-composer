#!/usr/bin/env python3
"""Read-only runtime validation for the isolated CHE add-on test."""
import json
from pathlib import Path
import subprocess
import sys

PROJECT = "chetest_addon"

EXPECTED = {
    "capcomposer": ("chetest_addon_app", "chetest_addon_app"),
    "capcomposer_db": ("chetest_addon_db", "postgis/postgis:15-master"),
    "capcomposer_redis": ("chetest_addon_redis", "redis:alpine"),
    "capcomposer_web_proxy": ("chetest_addon_proxy", "nginx:1.20.2-alpine"),
}


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Command failed: " + command[0])
    return result.stdout


def main():
    data_root = (
        Path(__file__).resolve().parent.parent / "test-data"
    ).resolve()

    try:
        ids = run([
            "docker", "ps", "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format", "{{.ID}}",
        ]).split()

        if len(ids) != len(EXPECTED):
            raise RuntimeError("Unexpected number of running test containers")

        containers = json.loads(run(["docker", "inspect", *ids]))
        seen = set()

        for container in containers:
            labels = container["Config"].get("Labels") or {}
            service = labels.get("com.docker.compose.service")
            project = labels.get("com.docker.compose.project")

            if project != PROJECT or service not in EXPECTED or service in seen:
                raise RuntimeError("Unexpected Docker project or service")

            seen.add(service)
            expected_name, expected_image = EXPECTED[service]

            if (
                container["Name"].lstrip("/") != expected_name
                or container["Config"]["Image"] != expected_image
                or not container["State"]["Running"]
            ):
                raise RuntimeError("Container identity mismatch: " + service)

            if service == "capcomposer_db":
                mounts = [
                    mount for mount in container.get("Mounts", [])
                    if mount.get("Destination") == "/var/lib/postgresql/data"
                    and mount.get("Type") == "bind"
                    and Path(mount["Source"]).resolve() == data_root / "db"
                ]
                if len(mounts) != 1:
                    raise RuntimeError("PostgreSQL storage is not isolated")

            print("PASS: Running Docker identity:", service)

        if seen != set(EXPECTED):
            raise RuntimeError("Expected Docker services missing")

        target = (
            Path(__file__).resolve().parent.parent / "test-cap-source"
        ).resolve()

        compose_command = [
            "docker", "compose", "-p", PROJECT,
            "-f", "docker-compose.yml",
            "-f", "docker-compose.test.yml",
            "config", "--format", "json",
        ]

        compose_result = subprocess.run(
            compose_command,
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )

        if compose_result.returncode:
            raise RuntimeError("Cannot resolve Docker Compose configuration")

        compose_config = json.loads(compose_result.stdout)
        compose_services = compose_config["services"]

        for container in containers:
            labels = container["Config"].get("Labels") or {}
            service = labels["com.docker.compose.service"]

            expected_mounts = {
                (
                    str(Path(mount["source"]).resolve()),
                    mount["target"],
                )
                for mount in compose_services[service].get("volumes", [])
                if isinstance(mount, dict) and mount.get("type") == "bind"
            }

            actual_mounts = {
                (
                    str(Path(mount["Source"]).resolve()),
                    mount["Destination"],
                )
                for mount in container.get("Mounts", [])
                if mount.get("Type") == "bind"
            }

            if actual_mounts != expected_mounts:
                raise RuntimeError(
                    "Running bind mounts differ from Compose: " + service
                )

            print("PASS: Runtime bind mounts:", service)

        sql = "SELECT current_database(), current_user"
        identity = run([
            "docker", "exec", "chetest_addon_db",
            "psql", "-X", "-U", "chetest_addon",
            "-d", "chetest_addon", "-At",
            "-v", "ON_ERROR_STOP=1",
            "-c", sql,
        ]).strip()

        if identity != "chetest_addon|chetest_addon":
            raise RuntimeError("Unexpected PostgreSQL database identity")

        print("PASS: Isolated PostgreSQL database identity")

        django_code = (
            "import os; "
            "os.environ.setdefault("
            "'DJANGO_SETTINGS_MODULE', "
            "'capcomposer.config.settings.production'); "
            "import django; django.setup(); "
            "from django.db import connection; "
            "cursor = connection.cursor(); "
            "cursor.execute("
            "'SELECT current_database(), current_user'); "
            "print('|'.join(cursor.fetchone()))"
        )

        django_result = run([
            "docker", "exec", "chetest_addon_app",
            "python", "-c", django_code,
        ])

        django_identity = django_result.strip().splitlines()[-1]

        if django_identity != "chetest_addon|chetest_addon":
            raise RuntimeError("Django is connected to an unexpected database")

        print("PASS: Django application uses the isolated CAP database")
        print("INSTALLATION NOT AUTHORIZED: Runtime verification only")
        return 0

    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL: Runtime validation:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
