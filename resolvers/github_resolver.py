#!/usr/bin/env python3
"""GitHub Issues/PR reference_materials resolver.

## RESOLVER CONVENTION

The reference_materials field stores a single GitHub issue or pull request URL.

Single URL (string):
  "https://github.com/owner/repo/issues/123"

The output is a JSON object with two keys:
  - "issue": the verbatim API response for the issue/PR
  - "comments": the verbatim API response for the comments (an array)

JSON arrays are not supported. If a JSON array is provided, the resolver will exit with an error.
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


def fetch_issue(hostname, owner, repo, number):
    """Fetch issue metadata and comments via gh api. Returns dict with issue and comments keys."""
    base_cmd = ["gh", "api"]
    if hostname != "github.com":
        base_cmd += ["--hostname", hostname]

    # Fetch issue/PR metadata
    issue_path = f"/repos/{owner}/{repo}/issues/{number}"
    try:
        issue_result = subprocess.run(
            base_cmd + [issue_path], capture_output=True, text=True
        )
    except OSError as exc:
        print(f"Failed to execute gh: {exc}", file=sys.stderr)
        sys.exit(1)
    if issue_result.returncode != 0:
        stderr_output = issue_result.stderr.strip()
        if "404" in stderr_output or "Not Found" in stderr_output:
            print(
                f"GitHub issue/PR not found: {owner}/{repo}#{number}",
                file=sys.stderr,
            )
        else:
            print(stderr_output or "gh api call failed", file=sys.stderr)
        sys.exit(issue_result.returncode)

    # Fetch comments
    comments_path = f"/repos/{owner}/{repo}/issues/{number}/comments"
    try:
        comments_result = subprocess.run(
            base_cmd + [comments_path], capture_output=True, text=True
        )
    except OSError as exc:
        print(f"Failed to fetch comments: {exc}", file=sys.stderr)
        sys.exit(1)
    if comments_result.returncode != 0:
        stderr_output = comments_result.stderr.strip()
        print(stderr_output or "gh api call failed for comments", file=sys.stderr)
        sys.exit(comments_result.returncode)

    return {
        "issue": json.loads(issue_result.stdout),
        "comments": json.loads(comments_result.stdout),
    }


def main():
    parser = argparse.ArgumentParser(description="Resolve GitHub issue/PR reference_materials values")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--value", required=True, help="reference_materials field value (URL string or 'null')")
    args = parser.parse_args()

    value = args.value

    # Null handling — before any parsing or network calls
    if value == "null":
        print("null")
        sys.exit(0)

    # gh availability check
    if shutil.which("gh") is None:
        print("gh is not installed or not on PATH", file=sys.stderr)
        sys.exit(1)

    # Reject JSON arrays — only single URLs are supported
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            print("JSON arrays are not supported; provide a single GitHub URL", file=sys.stderr)
            sys.exit(1)
    except (json.JSONDecodeError, TypeError):
        pass

    # Single URL
    try:
        hostname, owner, repo, number = parse_github_url(value)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(fetch_issue(hostname, owner, repo, number)))

    sys.exit(0)


if __name__ == "__main__":
    main()
