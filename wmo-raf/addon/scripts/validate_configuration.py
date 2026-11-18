#!/usr/bin/env python3
"""Read-only Docker configuration validation for isolated CHE add-on testing.

This initial implementation is deliberately restricted to the test installation.
It does not authorize CHE installation.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PROJECT = "chetest_addon"
REQUIRED_SERVICES = {
    "capcomposer",
    "capcomposer_db",
    "capcomposer_redis",
    "capcomposer_web_proxy",
    "capcomposer_celery_worker",
    "capcomposer_celery_beat",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="CAP Composer source directory")
    args = parser.parse_args()

    addon_root = Path(__file__).resolve().parent.parent
    expected_target = (addon_root / "test-cap-source").resolve()
    target = Path(args.target).expanduser().resolve()
    data_root = (addon_root / "test-data").resolve()

    if target != expected_target or not target.is_dir():
        print("FAIL: Target is not the isolated CHE add-on test installation")
        return 1

    command = [
        "docker", "compose",
        "-p", PROJECT,
        "-f", "docker-compose.yml",
        "-f", "docker-compose.test.yml",
        "config", "--format", "json",
    ]

    result = subprocess.run(
        command,
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode:
        print("FAIL: Docker Compose configuration cannot be resolved")
        return 1

    try:
        config = json.loads(result.stdout)
        services = config["services"]
    except (ValueError, KeyError, TypeError):
        print("FAIL: Invalid Docker Compose configuration")
        return 1

    if config.get("name") != PROJECT:
        print("FAIL: Unexpected Docker project")
        return 1

    if set(services) != REQUIRED_SERVICES:
        print("FAIL: Unexpected Docker service inventory")
        return 1

    app = services["capcomposer"]
    environment = app.get("environment", {})

    if not isinstance(environment, dict):
        print("FAIL: Unexpected application environment format")
        return 1

    for key in ("MIGRATE_ON_STARTUP", "COLLECT_STATICFILES_ON_STARTUP"):
        if str(environment.get(key, "")).lower() != "false":
            print("FAIL: Unsafe application startup setting:", key)
            return 1

    expected_images = {
        "capcomposer": "chetest_addon_app",
        "capcomposer_celery_worker": "chetest_addon_worker",
        "capcomposer_celery_beat": "chetest_addon_beat",
    }

    for service, expected_image in expected_images.items():
        if services[service].get("image") != expected_image:
            print("FAIL: Unexpected image for service:", service)
            return 1

    expected_mounts = {
        "/var/lib/postgresql/data": data_root / "db",
        "/wagtail_static": data_root / "static",
        "/wagtail_media": data_root / "media",
        "/etc/nginx/nginx.conf": target / "nginx/nginx.conf",
        "/capcomposer/app/src/capcomposer/static": data_root / "static",
        "/capcomposer/app/src/capcomposer/media": data_root / "media",
        "/capcomposer/app/src/capcomposer/backup": data_root / "backup",
    }

    checked_mounts = 0

    for service_name, service in services.items():
        for mount in service.get("volumes", []):
            if not isinstance(mount, dict) or mount.get("type") != "bind":
                continue

            destination = mount.get("target")
            source = mount.get("source")

            if not isinstance(source, str) or destination not in expected_mounts:
                print("FAIL: Unexpected bind mount in:", service_name)
                return 1

            if Path(source).resolve() != expected_mounts[destination]:
                print("FAIL: Unsafe bind mount in:", service_name)
                return 1

            checked_mounts += 1

    if checked_mounts < 10:
        print("FAIL: Expected isolated storage mounts are missing")
        return 1

    for service_name, service in services.items():
        ports = service.get("ports", [])

        if service_name == "capcomposer_web_proxy":
            if len(ports) != 1 or str(ports[0].get("published")) != "8083":
                print("FAIL: Unexpected Nginx published port")
                return 1
        elif ports:
            print("FAIL: Unexpected published ports in:", service_name)
            return 1

    print("PASS: Isolated Docker project and service inventory")
    print("PASS: Automatic application migrations disabled")
    print("PASS: Automatic static collection disabled")
    print("PASS: Dedicated application and Celery image names")
    print("PASS: Isolated bind-mount paths")
    print("PASS: Published ports restricted to test Nginx port 8083")
    print("NOTE: Running container and database identity require separate validation")
    print("INSTALLATION NOT AUTHORIZED: Configuration validation only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
