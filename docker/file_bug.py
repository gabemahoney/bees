#!/usr/bin/env python3
"""File a bug ticket against a remote bees MCP server over HTTP.
Needed because we cannot use the prod bees server when configured to use the in-test bees server.
This allows Claude in the docker to file bugs.

The bug goes into the host's bugs hive for the host's repo root. Hive names and paths differ between
machines, so neither is built in: run_test.sh finds both on the host and passes them into the
container as BEES_BUGS_HIVE and BEES_REPO_ROOT.

- Repo root: --repo-root, else $BEES_REPO_ROOT. Required: the server picks the hives by it.
- Hive: --hive, else $BEES_BUGS_HIVE, else asked from the server: list_hives for the repo root,
  then the same rule as run_test.sh (ci_bugs_hive.py, which goes by each hive's scope).
- Status: asked from the server too (get_status_values for the repo root), as status names differ
  between hives. The bug gets the first of the hive's status values (draft in an Apiary Bugs hive),
  and no status when the hive's status is freeform: bees refuses a status not among the values,
  and a missing one when there are values.

The whole exchange with the server gets FILE_BUG_TIMEOUT_SECONDS: a server that accepts the
connection but never answers must not hold the phase until /ci's deadline.

Usage:
    python file_bug.py --title TITLE --description DESC
    python file_bug.py --url URL --hive HIVE --repo-root PATH --title TITLE --description DESC

Prints "BUG FILED: <ticket-id>" on success. On failure, prints "BUG FILING FAILED: <reason>"
on stderr and exits 1.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from typing import NoReturn

import anyio
from ci_bugs_hive import choose_bugs_hive
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_BUG_SERVER_URL = "http://host.docker.internal:8473"
# Time for the whole exchange with the server: connect, initialize, list_hives, get_status_values, create_ticket.
FILE_BUG_TIMEOUT_SECONDS = 60


class BugFilingError(Exception):
    """The bug could not be filed. The message says why."""


async def _call_tool(session: ClientSession, tool: str, arguments: dict) -> dict:
    """Call a bees MCP tool and return its JSON result. Raises BugFilingError unless its status is success."""
    result = await session.call_tool(tool, arguments)
    # result.content is a list of TextContent objects
    for block in result.content:
        if hasattr(block, "text"):
            if not block.text.strip():
                raise BugFilingError(f"{tool}: empty text block")
            try:
                data = json.loads(block.text)
            except json.JSONDecodeError:
                raise BugFilingError(f"{tool}: non-JSON response: {block.text!r}") from None
            if data.get("status") != "success":
                raise BugFilingError(f"{tool}: {data}")
            return data
    raise BugFilingError(f"{tool}: no text content in response")


async def _discover_bugs_hive(session: ClientSession, repo_root: str) -> str:
    """Return the bugs hive among the hives the server lists for ``repo_root``."""
    listed = await _call_tool(session, "list_hives", {"repo_root": repo_root})
    # Each entry names its owning scope; the rule needs it, and the repo root they were listed for.
    hive, reason = choose_bugs_hive(listed.get("hives", []), repo_root)
    if hive is None:
        raise BugFilingError(f"no bugs hive for repo root {repo_root}: {reason}. Set BEES_BUGS_HIVE or pass --hive")
    return hive


def normalize_hive_name(hive_name: str) -> str:
    """bees' normalized form of a hive name (id_utils.normalize_hive_name), as the server keys its hives.

    Copied unchanged in behavior, like ci_bugs_hive.py's scope rule: the docker scripts do not import bees.
    """
    normalized = re.sub(r"[^a-z0-9_]", "", hive_name.lower().replace(" ", "_").replace("-", "_"))
    if normalized and not normalized[0].isalpha() and normalized[0] != "_":
        normalized = "_" + normalized
    return normalized


async def _new_bug_status(session: ClientSession, repo_root: str, hive: str) -> str | None:
    """Return the first of ``hive``'s status values, or None when its status is freeform.

    The values are resolved as bees does (config.resolve_status_values_for_hive): the hive's own,
    else the scope's, else the global ones. get_status_values shows a hive whose status_values is
    null (freeform, nothing inherited) like one without any, so such a hive gets the scope's or
    global first value, which its freeform status accepts.
    """
    levels = await _call_tool(session, "get_status_values", {"repo_root": repo_root})
    for values in (levels.get("hives", {}).get(normalize_hive_name(hive)), levels.get("scope"), levels.get("global")):
        if values:
            return values[0]
    return None


async def file_bug(url: str, title: str, description: str, repo_root: str, hive: str | None = None) -> str:
    """File the bug and return its ticket ID. Raises BugFilingError when the server rejects it."""
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            # Leave the MCP client's task groups before raising: they would wrap the error in an exception group.
            try:
                if hive is None:
                    hive = await _discover_bugs_hive(session, repo_root)
                ticket = {
                    "ticket_type": "bee",
                    "title": title,
                    "hive": hive,
                    "body": description,
                    "repo_root": repo_root,
                }
                status = await _new_bug_status(session, repo_root, hive)
                if status is not None:
                    ticket["status"] = status
                created = await _call_tool(session, "create_ticket", ticket)
            except BugFilingError as exc:
                error = exc
            else:
                return created["ticket_id"]
    raise error


async def file_bug_in_time(
    url: str, title: str, description: str, repo_root: str, hive: str | None, timeout: float
) -> str:
    """file_bug, given up after ``timeout`` seconds with a BugFilingError."""
    # An anyio cancel scope, not asyncio.wait_for: wait_for also waits for the MCP client's cleanup,
    # whose session DELETE to a server that stopped answering only ends at httpx's 300 s read
    # timeout. The cancel scope cancels that cleanup too, so the limit holds.
    with anyio.move_on_after(timeout):
        return await file_bug(url, title, description, repo_root, hive)
    raise BugFilingError(f"no answer from the bees server at {url} within {timeout:g} s")


def _describe(exc: BaseException) -> str:
    """One line naming the innermost errors: the MCP client wraps connection errors in exception groups."""
    nested = getattr(exc, "exceptions", None)
    if nested:
        return "; ".join(_describe(inner) for inner in nested)
    return f"{type(exc).__name__}: {exc}"


def _fail(reason: str) -> NoReturn:
    print(f"BUG FILING FAILED: {reason}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="File a bug via bees MCP HTTP server")
    parser.add_argument("--url", default=None, help="MCP server URL (default: $BUG_SERVER_URL/mcp)")
    parser.add_argument("--title", required=True, help="Bug title")
    parser.add_argument("--description", required=True, help="Bug description")
    parser.add_argument(
        "--hive",
        default=None,
        help="Bugs hive to file into (default: $BEES_BUGS_HIVE, else discovered from the server's hives)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Host repo root the bees server picks the hives by (default: $BEES_REPO_ROOT)",
    )
    args = parser.parse_args()

    url = args.url or os.environ.get("BUG_SERVER_URL", DEFAULT_BUG_SERVER_URL) + "/mcp"
    hive = args.hive or os.environ.get("BEES_BUGS_HIVE") or None
    repo_root = args.repo_root or os.environ.get("BEES_REPO_ROOT")
    if not repo_root:
        _fail(
            "no repo root: set BEES_REPO_ROOT or pass --repo-root with the host path whose bees scope holds "
            "the bugs hive (run_test.sh sets it)"
        )

    try:
        ticket_id = asyncio.run(
            file_bug_in_time(url, args.title, args.description, repo_root, hive, FILE_BUG_TIMEOUT_SECONDS)
        )
    except BugFilingError as exc:
        _fail(str(exc))
    except Exception as exc:  # connection and protocol errors must end in the failure line too
        _fail(f"cannot file the bug through the bees server at {url}: {_describe(exc)}")
    print(f"BUG FILED: {ticket_id}")


if __name__ == "__main__":
    main()
