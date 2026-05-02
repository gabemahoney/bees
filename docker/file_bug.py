#!/usr/bin/env python3
"""File a bug ticket against a remote bees MCP server over HTTP.
Needed because we cannot use the prod bees server when configured to use the in-test bees server.
This allows Claude in the docker to file bugs.

Usage:
    python file_bug.py --url URL --title TITLE --description DESC
    python file_bug.py --title TITLE --description DESC   # uses $BUG_SERVER_URL

Prints the ticket ID on success, exits non-zero on failure.
"""
import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def file_bug(url: str, title: str, description: str, repo_root: str) -> str:
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_ticket",
                {
                    "ticket_type": "bee",
                    "title": title,
                    "hive": "bees_bugs",
                    "status": "open",
                    "body": description,
                    "repo_root": repo_root,
                },
            )
            # result.content is a list of TextContent objects
            for block in result.content:
                if hasattr(block, "text"):
                    if not block.text.strip():
                        print(f"ERROR: Empty text block", file=sys.stderr)
                        sys.exit(1)
                    try:
                        data = json.loads(block.text)
                    except json.JSONDecodeError:
                        print(f"ERROR: Non-JSON response: {block.text!r}", file=sys.stderr)
                        sys.exit(1)
                    if data.get("status") == "success":
                        return data["ticket_id"]
                    else:
                        print(f"ERROR: {data}", file=sys.stderr)
                        sys.exit(1)
            print("ERROR: No text content in response", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="File a bug via bees MCP HTTP server")
    parser.add_argument("--url", default=None, help="MCP server URL (default: $BUG_SERVER_URL/mcp)")
    parser.add_argument("--title", required=True, help="Bug title")
    parser.add_argument("--description", required=True, help="Bug description")
    parser.add_argument("--repo-root", default=None, help="Repo root for the bees server (default: $BEES_REPO_ROOT)")
    args = parser.parse_args()

    url = args.url or os.environ.get("BUG_SERVER_URL", "http://host.docker.internal:8000") + "/mcp"
    repo_root = args.repo_root or os.environ.get("BEES_REPO_ROOT", "/home/gmahoney/projects/bees_project")

    ticket_id = asyncio.run(file_bug(url, args.title, args.description, repo_root))
    print(f"BUG FILED: {ticket_id}")


if __name__ == "__main__":
    main()
