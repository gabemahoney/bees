"""Built-in reference_materials resolvers for the Bees ticket management system.

Provides sync Python implementations of the GitHub and Bees resolvers so that
pipx-installed users don't need external scripts on PATH.
"""

import json
import re
import shutil
import subprocess


# ---------------------------------------------------------------------------
# Resolver convention strings
# ---------------------------------------------------------------------------

GITHUB_RESOLVER_CONVENTION = (
    "Accepts a single GitHub issue or pull request URL string. "
    "Example: \"https://github.com/owner/repo/issues/123\". "
    "JSON arrays are not supported. "
    "Returns {\"issue\": <API response>, \"comments\": <comments array>} on success. "
    "Requires the gh CLI to be installed and authenticated. "
    "Returns {\"status\": \"error\", \"raw_value\": value, \"error\": str} on failure."
)

BEES_RESOLVER_CONVENTION = (
    "Accepts a Bee ID string (e.g. \"b.ABC\") that links a ticket back to the "
    "idea that spawned it. This resolver is an identity function — it returns "
    "the value unchanged as {\"status\": \"success\", \"value\": value}."
)

# ---------------------------------------------------------------------------
# GitHub URL parsing (moved from resolvers/github_resolver.py)
# ---------------------------------------------------------------------------

_GITHUB_URL_PATTERN = re.compile(
    r"^https?://([^/]+)/([^/]+)/([^/]+)/(issues|pull)/(\d+)$"
)


def _parse_github_url(url: str) -> tuple[str, str, str, int]:
    """Parse a GitHub issue/PR URL into (hostname, owner, repo, number).

    Raises:
        ValueError: If the URL is not a valid GitHub issue or PR URL.
    """
    match = _GITHUB_URL_PATTERN.match(url.strip())
    if not match:
        raise ValueError(f"Not a valid GitHub issue or PR URL: {url}")

    hostname, owner, repo, _kind, number_str = match.groups()
    number = int(number_str)
    if number <= 0:
        raise ValueError(f"Issue/PR number must be positive, got: {number}")

    return hostname, owner, repo, number


def _fetch_issue(hostname: str, owner: str, repo: str, number: int) -> dict:
    """Fetch issue metadata and comments via gh api.

    Returns:
        {"issue": ..., "comments": ...}

    Raises:
        RuntimeError: On gh execution errors or non-zero exit codes.
    """
    base_cmd = ["gh", "api"]
    if hostname != "github.com":
        base_cmd += ["--hostname", hostname]

    issue_path = f"/repos/{owner}/{repo}/issues/{number}"
    issue_result = subprocess.run(
        base_cmd + [issue_path], capture_output=True, text=True
    )
    if issue_result.returncode != 0:
        stderr_output = issue_result.stderr.strip()
        if "404" in stderr_output or "Not Found" in stderr_output:
            raise RuntimeError(f"GitHub issue/PR not found: {owner}/{repo}#{number}")
        raise RuntimeError(stderr_output or "gh api call failed")

    comments_path = f"/repos/{owner}/{repo}/issues/{number}/comments"
    comments_result = subprocess.run(
        base_cmd + [comments_path], capture_output=True, text=True
    )
    if comments_result.returncode != 0:
        stderr_output = comments_result.stderr.strip()
        raise RuntimeError(stderr_output or "gh api call failed for comments")

    return {
        "issue": json.loads(issue_result.stdout),
        "comments": json.loads(comments_result.stdout),
    }


# ---------------------------------------------------------------------------
# Public resolver functions
# ---------------------------------------------------------------------------


def resolve_github(value: object) -> dict:
    """Resolve a GitHub issue or PR URL to its metadata.

    Sync wrapper around ``_fetch_issue`` that handles error cases gracefully.
    Designed to be called via ``asyncio.to_thread`` from async contexts.

    Args:
        value: The reference_materials entry value (expected: a URL string).

    Returns:
        On success: {"issue": ..., "comments": ...}
        On error: {"status": "error", "raw_value": value, "error": str}
    """
    if not isinstance(value, str):
        return {
            "status": "error",
            "raw_value": value,
            "error": "value must be a string GitHub URL",
        }

    # Check gh availability
    if shutil.which("gh") is None:
        return {
            "status": "error",
            "raw_value": value,
            "error": "gh is not installed or not on PATH",
        }

    # Reject JSON arrays — only single URLs are supported
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return {
                "status": "error",
                "raw_value": value,
                "error": "JSON arrays are not supported; provide a single GitHub URL",
            }
    except (json.JSONDecodeError, TypeError):
        pass

    try:
        hostname, owner, repo, number = _parse_github_url(value)
    except ValueError as exc:
        return {"status": "error", "raw_value": value, "error": str(exc)}

    try:
        result = _fetch_issue(hostname, owner, repo, number)
    except RuntimeError as exc:
        return {"status": "error", "raw_value": value, "error": str(exc)}

    return result


def resolve_bee(value: object) -> dict:
    """Resolve a Bee ID reference_materials value (identity function).

    The bee resolver returns the value unchanged — it simply records which
    Bee ID this ticket is linked to.

    Args:
        value: The reference_materials entry value (expected: a Bee ID string).

    Returns:
        {"status": "success", "value": value}
    """
    return {"status": "success", "value": value}
