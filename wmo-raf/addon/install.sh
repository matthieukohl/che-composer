#!/bin/sh
# CHE Composer add-on: development-only Terminal launcher.
# Real national deployments are NOT authorized by this script.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

# Read-only national deployment preflight.
# National installation remains disabled.
if [ "$#" -eq 3 ] && [ "$1" = "preflight" ] && [ "$2" = "--config" ]; then
    exec /usr/bin/python3 "$SCRIPT_DIR/scripts/preflight_portable_deployment.py" \
        --config "$3"
fi

# Read-only national CAP source planning.
# This does not authorize installation.
if [ "$#" -eq 3 ] && [ "$1" = "plan" ] && [ "$2" = "--cap-path" ]; then
    exec /usr/bin/python3 "$SCRIPT_DIR/scripts/plan_packaged_install_transaction.py" "$3"
fi

# Portable-path execution remains restricted by the Python engines
# to disposable, known test fixtures. Not a production installer.
if [ "$#" -eq 3 ] && [ "$2" = "--cap-path" ]; then
    case "$1" in
        install)
            exec /usr/bin/python3 "$SCRIPT_DIR/scripts/execute_packaged_test_transaction.py" \
                --cap-path "$3"
            ;;
        recover)
            exec /usr/bin/python3 "$SCRIPT_DIR/scripts/recover_source_from_journal.py" \
                --cap-path "$3"
            ;;
    esac
fi

# National install first runs the complete read-only deployment preflight.
# Deliberately fail closed afterward until the transaction is authorized.
if [ "$#" -eq 3 ] && [ "$1" = "install" ] && [ "$2" = "--config" ]; then
    if ! /usr/bin/python3 "$SCRIPT_DIR/scripts/preflight_portable_deployment.py" --config "$3"; then
        printf '%s\n' "FAIL: National deployment preflight did not pass." >&2
        printf '%s\n' "INSTALLATION NOT AUTHORIZED" >&2
        exit 1
    fi
    # The preflight passed. Read the CAP project root from the same config.
    # The transaction engine independently enforces disposable test roots.
    cap_path=$(/usr/bin/python3 -c '
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text())
    value = data["cap_path"]
    if (not isinstance(value, str) or not value.startswith("/")
            or "\\n" in value or "\\r" in value):
        raise ValueError("Unsafe CAP project path")
    print(value)
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)
' "$3") || {
        printf '%s\n' "FAIL: Cannot read a safe CAP project path from config." >&2
        printf '%s\n' "INSTALLATION NOT AUTHORIZED" >&2
        exit 1
    }

    # Still test-only: the executor rejects all operational project roots.
    exec /usr/bin/python3 "$SCRIPT_DIR/scripts/execute_packaged_test_transaction.py" \
        --cap-path "$cap_path"
fi

# Emergency source recovery does not require Docker/database preflight.
# The recovery engine independently restricts writes to test fixtures.
if [ "$#" -eq 3 ] && [ "$1" = "recover" ] && [ "$2" = "--config" ]; then
    cap_path=$(/usr/bin/python3 -c '
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text())
    value = data["cap_path"]
    if (not isinstance(value, str) or not value.startswith("/")
            or "\n" in value or "\r" in value):
        raise ValueError("Unsafe CAP project path")
    print(value)
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)
' "$3") || {
        printf '%s\n' "FAIL: Cannot read a safe CAP project path from config." >&2
        printf '%s\n' "RECOVERY NOT STARTED" >&2
        exit 1
    }
    exec /usr/bin/python3 "$SCRIPT_DIR/scripts/recover_source_from_journal.py" \
        --cap-path "$cap_path"
fi

# Read-only planning from the same deployment configuration.
# Planning is not installation authorization.
if [ "$#" -eq 3 ] && [ "$1" = "plan" ] && [ "$2" = "--config" ]; then
    cap_path=$(/usr/bin/python3 -c '
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text())
    value = data["cap_path"]
    if (not isinstance(value, str) or not value.startswith("/")
            or "\n" in value or "\r" in value):
        raise ValueError("Unsafe CAP project path")
    print(value)
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)
' "$3") || {
        printf '%s\n' "FAIL: Cannot read a safe CAP project path from config." >&2
        printf '%s\n' "PLANNING NOT STARTED" >&2
        exit 1
    }
    exec /usr/bin/python3 "$SCRIPT_DIR/scripts/plan_packaged_install_transaction.py" \
        "$cap_path"
fi

if [ "$#" -ne 3 ] || [ "$2" != "--workspace" ]; then
    printf '%s\n' "Usage: ./install.sh {plan|install|recover} --workspace DISPOSABLE_TEST_PATH" >&2
    printf '%s\n' "TEST ONLY: National deployment is not yet enabled." >&2
    exit 2
fi

case "$1" in
    plan|install|recover) ;;
    *)
        printf '%s\n' "FAIL: Unknown action." >&2
        exit 2
        ;;
esac

exec /usr/bin/python3 "$SCRIPT_DIR/scripts/che_addon_test_installer.py" \
    "$1" --workspace "$3"
