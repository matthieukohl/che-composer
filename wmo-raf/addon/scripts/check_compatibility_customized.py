#!/usr/bin/env python3
"""Read-only compatibility checks for WMO-RAF CAP Composer."""
import argparse
import pathlib
import subprocess
import sys

EXPECTED_VERSION = "1.3.6"
EXPECTED_COMMIT = "527751b04903e67dd6419750a157ec32e6940756"

def check_target(root):
    problems = []
    warnings = []

    required = [
        "Dockerfile",
        "capcomposer/pyproject.toml",
        "capcomposer/src/capcomposer/config/settings/base.py",
        "capcomposer/src/capcomposer/config/urls.py",
        "capcomposer/docker/docker-entrypoint.sh",
    ]

    for relative in required:
        if not (root / relative).is_file():
            problems.append("Missing required file: " + relative)

    che_path = root / "capcomposer/src/capcomposer/che"
    if che_path.exists():
        problems.append("CHE application directory already exists")

    settings = root / required[2]
    urls = root / required[3]

    if settings.is_file():
        content = settings.read_text()
        if '"capcomposer.che"' in content:
            problems.append("CHE is already registered in settings")

    if urls.is_file():
        content = urls.read_text()
        if "capcomposer.che.urls" in content:
            problems.append("CHE routes are already registered")

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        if result.returncode != 0 or pathlib.Path(result.stdout.strip()).resolve() != root:
            warnings.append(
                "Target has no independent Git repository; "
                "upstream version and file verification required"
            )
            result = None

        if result is not None:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        if result is not None and result.returncode == 0:
            commit = result.stdout.strip()
            if commit != EXPECTED_COMMIT:
                warnings.append(
                    "Git HEAD differs from verified upstream baseline: " + commit
                )
        elif result is not None:
            warnings.append("Git commit cannot be verified")
    except OSError:
        warnings.append("Git command unavailable")

    version_file = (
        root / "capcomposer/src/capcomposer/version.py"
    )
    if not version_file.is_file():
        problems.append("CAP Composer version file is missing")
    else:
        import ast
        try:
            tree = ast.parse(version_file.read_text())
            versions = [
                ast.literal_eval(node.value)
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "VERSION"
                    for target in node.targets
                )
            ]
            if len(versions) != 1:
                problems.append("Cannot determine CAP Composer version")
            elif versions[0] != (1, 3, 6, "final", 0):
                problems.append(
                    "Unsupported CAP Composer version: " + str(versions[0])
                )
            else:
                print("PASS: CAP Composer version 1.3.6")
        except (SyntaxError, ValueError, TypeError, OSError):
            problems.append("Cannot safely parse CAP Composer version")

    # Validate critical files against the published upstream manifest.
    import json
    import hashlib

    manifest_path = (
        pathlib.Path(__file__).resolve().parent.parent
        / "integration/upstream_manifest.json"
    )

    if not manifest_path.is_file():
        problems.append("Upstream compatibility manifest is missing")
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
            if (
                manifest.get("version") != EXPECTED_VERSION
                or manifest.get("commit") != EXPECTED_COMMIT
            ):
                problems.append("Invalid upstream compatibility manifest")
            else:
                patchable = {
                    "capcomposer/src/capcomposer/config/settings/base.py",
                    "capcomposer/src/capcomposer/config/urls.py",
                    "capcomposer/src/capcomposer/config/templates/wagtailadmin/base.html",
                }
                for relative, expected_hash in manifest["sha256"].items():
                    target_file = root / relative
                    if target_file.is_symlink() or not target_file.is_file():
                        problems.append("Missing or unsafe upstream file: " + relative)
                    elif relative in patchable:
                        print("INFO: Targeted compatibility check required:", relative)
                    elif hashlib.sha256(
                        target_file.read_bytes()
                    ).hexdigest() != expected_hash:
                        problems.append(
                            "Modified upstream file requires review: "
                            + relative
                        )
                    else:
                        print("PASS: Upstream file verified:", relative)

                if patchable != set(manifest["sha256"]) - {
                    "Dockerfile",
                    "capcomposer/pyproject.toml",
                    "capcomposer/docker/docker-entrypoint.sh",
                }:
                    problems.append("Unexpected compatibility manifest structure")
                else:
                    checker = pathlib.Path(__file__).resolve().parent / "check_customized_source.py"
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(checker),
                            str(root / "capcomposer/src/capcomposer"),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if result.returncode:
                        problems.append(
                            "Targeted CAP configuration compatibility failed: "
                            + (result.stdout.strip() or result.stderr.strip())
                        )
                    else:
                        print(result.stdout, end="")
        except (OSError, ValueError, KeyError, TypeError):
            problems.append("Cannot validate upstream compatibility manifest")

    # Missing independent Git metadata is informational once file
    # fingerprints and version have been independently verified.
    warnings = [
        warning for warning in warnings
        if "no independent Git repository" not in warning
    ]

    print("CHE Add-on — compatibility preflight")
    print("Target:", root)
    print("Supported baseline: WMO-RAF CAP Composer", EXPECTED_VERSION)
    print("Expected upstream commit:", EXPECTED_COMMIT)

    for warning in warnings:
        print("WARNING:", warning)

    for problem in problems:
        print("FAIL:", problem)

    if problems or warnings:
        print("RESULT: NOT APPROVED for automatic installation")
        return 1

    print("RESULT: Preliminary structural checks passed")
    print("NOTE: Backup verification and configuration checks still required")
    return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to existing CAP Composer source")
    args = parser.parse_args()
    root = pathlib.Path(args.target).expanduser().resolve()
    if not root.is_dir():
        print("ERROR: Target directory not found")
        return 1
    return check_target(root)

if __name__ == "__main__":
    sys.exit(main())
