#!/usr/bin/env python3
"""Read-only PostgreSQL structural comparison; not installation authorization."""

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

QUERIES = {
    "columns": """
        SELECT n.nspname, c.relname, a.attnum, a.attname,
               pg_catalog.format_type(a.atttypid,a.atttypmod),
               a.attnotnull, a.attidentity, a.attgenerated,
               pg_catalog.pg_get_expr(d.adbin,d.adrelid)
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_catalog.pg_attrdef d
               ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f')
          AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY n.nspname,c.relname,a.attnum
    """,
    "constraints": """
        SELECT n.nspname,c.relname,k.conname,k.contype,
               pg_catalog.pg_get_constraintdef(k.oid,true)
        FROM pg_catalog.pg_constraint k
        JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public'
        ORDER BY n.nspname,c.relname,k.conname
    """,
    "indexes": """
        SELECT schemaname,tablename,indexname,indexdef
        FROM pg_catalog.pg_indexes
        WHERE schemaname='public'
        ORDER BY schemaname,tablename,indexname
    """,
    "sequences": """
        SELECT schemaname,sequencename,data_type,start_value,min_value,
               max_value,increment_by,cycle,cache_size,last_value
        FROM pg_catalog.pg_sequences
        WHERE schemaname='public'
        ORDER BY schemaname,sequencename
    """,
    "views": """
        SELECT schemaname,viewname,definition
        FROM pg_catalog.pg_views
        WHERE schemaname='public'
        ORDER BY schemaname,viewname
    """,
    "triggers": """
        SELECT n.nspname,c.relname,t.tgname,
               pg_catalog.pg_get_triggerdef(t.oid,true),t.tgenabled
        FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND NOT t.tgisinternal
        ORDER BY n.nspname,c.relname,t.tgname
    """,
    "extensions": """
        SELECT e.extname,e.extversion,n.nspname
        FROM pg_catalog.pg_extension e
        JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace
        ORDER BY e.extname
    """,
}


def fingerprint(args, database, category, query):
    # Every query is fixed internally. Only validated identifiers are inputs.
    sql = (
        "COPY (SELECT row_to_json(t)::text FROM ("
        + query.strip()
        + ") t) TO STDOUT /* CHE_SCHEMA:" + category + " */"
    )
    command = [
        "docker", "exec", args.container,
        "psql", "-X", "-U", args.db_user,
        "-d", database, "-v", "ON_ERROR_STOP=1",
        "-c", sql,
    ]
    digest = hashlib.sha256()
    rows = 0
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=errors
        )
        try:
            for line in process.stdout:
                digest.update(line)
                rows += 1
            process.stdout.close()
            status = process.wait(timeout=120)
        except BaseException:
            process.kill()
            process.wait()
            raise
        if status != 0:
            raise RuntimeError(
                "PostgreSQL inspection failed: " + database + "." + category
            )
    return rows, digest.hexdigest()


def compare(args):
    if not CONTAINER.fullmatch(args.container):
        raise ValueError("Unsafe PostgreSQL container name")
    for name in (args.db_user, args.original_db, args.restored_db):
        if not IDENTIFIER.fullmatch(name):
            raise ValueError("Unsafe PostgreSQL identifier")
    if args.original_db == args.restored_db:
        raise ValueError("Original and restored databases must differ")

    for category, query in QUERIES.items():
        original = fingerprint(args, args.original_db, category, query)
        restored = fingerprint(args, args.restored_db, category, query)
        if original != restored:
            raise RuntimeError("Restored structure differs: " + category)
        if category == "columns" and original[0] == 0:
            raise RuntimeError("Unexpectedly empty public column inventory")
        print("PASS: Structure matches:", category,
              "| entries:", original[0], flush=True)

    print("PASS: Seven structural inventories match")
    print("NOTE: Sequence state is comparable only when visible to the DB user")
    print("NOTE: Roles, permissions, non-public schemas, restore provenance")
    print("      and transaction-consistent snapshots require separate checks")
    print("INSTALLATION NOT AUTHORIZED: Partial schema comparison only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--original-db", required=True)
    parser.add_argument("--restored-db", required=True)
    args = parser.parse_args()
    try:
        compare(args)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
