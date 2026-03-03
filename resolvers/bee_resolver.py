#!/usr/bin/env python3
"""Bee ID egg resolver.

## RESOLVER CONVENTION

The egg field stores the ID of a Bee from the Ideas hive (e.g. "b.ABC").
This links a ticket in any hive back to the idea that spawned it.

This resolver is an identity function — it returns the Bee ID unchanged.
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Resolve Bee ID egg values")
    parser.add_argument("--repo-root", help="Repository root path")
    parser.add_argument("--egg-value", help="egg value (raw string)")
    args = parser.parse_args()

    if not args.repo_root or not args.egg_value:
        parser.error("--repo-root and --egg-value are required")

    try:
        egg_value = json.loads(args.egg_value)
    except (json.JSONDecodeError, TypeError):
        egg_value = args.egg_value

    print(json.dumps(egg_value))
    sys.exit(0)


if __name__ == "__main__":
    main()
