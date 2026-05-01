#!/usr/bin/env python3
"""GitHub Issues/PR egg resolver.

## RESOLVER CONVENTION

The egg field stores a GitHub issue or pull request URL.
Examples:
  - https://github.com/owner/repo/issues/123
  - https://github.com/owner/repo/pull/456
  - https://github.example.com/owner/repo/issues/789

This resolver invokes `gh api` to fetch the issue/PR data from the GitHub API
and returns the verbatim JSON response. The full API response is written
to stdout as raw JSON.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys


GITHUB_URL_PATTERN = re.compile(
    r"^https?://([^/]+)/([^/]+)/([^/]+)/(issues|pull)/(\d+)$"
)


def parse_github_url(url):
    """Parse a GitHub issue/PR URL into components.

    Returns (hostname, owner, repo, number) or raises ValueError.
    """
    match = GITHUB_URL_PATTERN.match(url.strip())
    if not match:
        raise ValueError(f"Not a valid GitHub issue or PR URL: {url}")

    hostname, owner, repo, _kind, number_str = match.groups()
    number = int(number_str)
    if number <= 0:
        raise ValueError(f"Issue/PR number must be positive, got: {number}")

    return hostname, owner, repo, number


def main():
    parser = argparse.ArgumentParser(description="Resolve GitHub issue/PR egg values")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--egg-value", required=True, help="Egg field value (raw string, or 'null')")
    args = parser.parse_args()

    egg_value = args.egg_value

    # Subtask 2: null handling — before any URL parsing or network calls
    if egg_value == "null":
        print("null")
        sys.exit(0)

    # Subtask 1: URL parsing
    try:
        hostname, owner, repo, number = parse_github_url(egg_value)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    # Subtask 3: gh availability check
    if shutil.which("gh") is None:
        print("gh is not installed or not on PATH", file=sys.stderr)
        sys.exit(1)

    # Subtask 3: API delegation
    api_path = f"/repos/{owner}/{repo}/issues/{number}"
    cmd = ["gh", "api", api_path]
    if hostname != "github.com":
        cmd += ["--hostname", hostname]

    # Subtask 4: gh error surfacing
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr_output = result.stderr.strip()
        if "404" in stderr_output or "Not Found" in stderr_output:
            print(
                f"GitHub issue/PR not found: {owner}/{repo}#{number}",
                file=sys.stderr,
            )
        else:
            print(stderr_output or "gh api call failed", file=sys.stderr)
        sys.exit(result.returncode)

    print(result.stdout, end="")
    sys.exit(0)


if __name__ == "__main__":
    main()
