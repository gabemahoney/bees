#!/usr/bin/env python3
"""Bee ID reference_materials resolver.

## RESOLVER CONVENTION

The reference_materials field stores the ID of a Bee from the Ideas hive (e.g. "b.ABC").
This links a ticket in any hive back to the idea that spawned it.

This resolver is an identity function — it returns the Bee ID unchanged.
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Resolve Bee ID reference_materials values")
    parser.add_argument("--repo-root", help="Repository root path")
    parser.add_argument("--value", help="reference_materials value (raw string)")
    args = parser.parse_args()

    if not args.repo_root or not args.value:
        parser.error("--repo-root and --value are required")

    try:
        value = json.loads(args.value)
    except (json.JSONDecodeError, TypeError):
        value = args.value

    print(json.dumps(value))
    sys.exit(0)


if __name__ == "__main__":
    main()
