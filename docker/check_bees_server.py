#!/usr/bin/env python3
"""Check that the HTTP server at a base URL is a bees MCP server.

A /health check is not enough: another service bound to the same port may
answer it too. This script sends an MCP ``initialize`` request to <base>/mcp
and accepts the server only if it reports ``serverInfo.name == "bees"``.

Stdlib only: it runs on the host with plain python3, where the ``mcp``
package may not be importable.

Usage:
    python3 check_bees_server.py http://127.0.0.1:8473
    python3 check_bees_server.py --url http://127.0.0.1:8473 --timeout 5 --wait 10

Exit codes:
    0  bees confirmed
    1  nothing listening: connection refused, host or network unreachable, or host name not resolved
    2  no bees MCP server answered, but the connection was not refused: another service answered,
       or the connection was reset, timed out or failed the TLS handshake
    3  usage error: missing or malformed URL (an http:// or https:// URL with a host and a port
       from 1 to 65535 is required), --timeout not a finite number > 0, or --wait not a finite number >= 0
"""

from __future__ import annotations

import argparse
import errno
import http.client
import json
import math
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

EXIT_BEES = 0
EXIT_NOT_LISTENING = 1
EXIT_NOT_BEES = 2
EXIT_USAGE = 3

EXPECTED_SERVER_NAME = "bees"
DEFAULT_TIMEOUT = 5.0
POLL_INTERVAL = 0.5
SESSION_HEADER = "mcp-session-id"

INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "bees-ci-check", "version": "1.0"},
    },
}

# Always talk to the URL directly; a proxy from the environment would hide which server holds the port.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# connect() errors that mean no server is reachable at the address. Any other error (reset, timeout,
# TLS failure) means the connection was not refused, so something other than bees may hold the port.
_NOT_LISTENING_ERRNOS = frozenset({errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ENETUNREACH})

# SSE lines end in CRLF, CR or LF only. str.splitlines() would also split on characters such as
# U+2028, which may appear unescaped inside a JSON data payload.
_SSE_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def _sse_data_payloads(body: str) -> list[str]:
    """Return the data payload of each event in an SSE stream (multi-line data joined with newlines)."""
    payloads = []
    data_lines: list[str] = []
    for line in _SSE_LINE_BREAK.split(body):
        if line.startswith("data:"):
            value = line[len("data:") :]
            data_lines.append(value[1:] if value.startswith(" ") else value)
        elif not line and data_lines:
            payloads.append("\n".join(data_lines))
            data_lines = []
    if data_lines:
        payloads.append("\n".join(data_lines))
    return payloads


def _decode_messages(body: str) -> list:
    """Decode a response body that is either plain JSON or an SSE stream of JSON messages."""
    try:
        return [json.loads(body)]
    except json.JSONDecodeError:
        pass
    messages = []
    for payload in _sse_data_payloads(body):
        try:
            messages.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return messages


def parse_server_name(body: str) -> str:
    """Return ``result.serverInfo.name`` from an MCP initialize response body.

    Accepts plain JSON or SSE (``event: message`` / ``data: {...}`` lines).
    Raises ValueError if the body holds no initialize result with a serverInfo name.
    """
    for message in _decode_messages(body):
        if not isinstance(message, dict):
            continue
        result = message.get("result")
        server_info = result.get("serverInfo") if isinstance(result, dict) else None
        name = server_info.get("name") if isinstance(server_info, dict) else None
        if isinstance(name, str):
            return name
    raise ValueError("response is not an MCP initialize result with serverInfo.name")


def _is_not_listening(reason: object) -> bool:
    """True if a URLError reason means no server is reachable (refused, unreachable or unresolved host)."""
    if isinstance(reason, socket.gaierror):
        return True
    return isinstance(reason, OSError) and reason.errno in _NOT_LISTENING_ERRNOS


def _close_session(mcp_url: str, session_id: str, timeout: float) -> None:
    """Best-effort DELETE so the check does not leave an idle MCP session on the server."""
    request = urllib.request.Request(mcp_url, headers={SESSION_HEADER: session_id}, method="DELETE")
    try:
        with _OPENER.open(request, timeout=timeout):
            pass
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        pass


def check_bees_server(base_url: str, timeout: float = DEFAULT_TIMEOUT) -> tuple[int, str]:
    """Send an MCP initialize request to <base_url>/mcp and report whether the server is bees.

    Returns (exit_code, reason): exit_code is EXIT_BEES, EXIT_NOT_LISTENING or EXIT_NOT_BEES,
    and reason is a one-line human-readable explanation.
    """
    mcp_url = base_url.rstrip("/") + "/mcp"
    request = urllib.request.Request(
        mcp_url,
        data=json.dumps(INITIALIZE_REQUEST).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            session_id = response.headers.get(SESSION_HEADER)
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return EXIT_NOT_BEES, f"{mcp_url} answered HTTP {exc.code} {exc.reason}: not a bees MCP server"
    except urllib.error.URLError as exc:
        # urllib wraps every OSError raised while connecting or sending, so check why the request failed.
        if _is_not_listening(exc.reason):
            return EXIT_NOT_LISTENING, f"no server reachable at {mcp_url} ({exc.reason})"
        return EXIT_NOT_BEES, f"request to {mcp_url} failed ({exc.reason}): no bees MCP server answered"
    except (http.client.HTTPException, OSError) as exc:
        return EXIT_NOT_BEES, f"{mcp_url} accepted the connection but sent no valid HTTP response ({exc!r})"

    if session_id:
        _close_session(mcp_url, session_id, timeout)

    try:
        name = parse_server_name(body)
    except ValueError as exc:
        return EXIT_NOT_BEES, f"{mcp_url} answered, but not as an MCP server: {exc}"
    if name != EXPECTED_SERVER_NAME:
        return EXIT_NOT_BEES, f"{mcp_url} is an MCP server named {name!r}, not {EXPECTED_SERVER_NAME!r}"
    return EXIT_BEES, f"bees MCP server confirmed at {mcp_url} (serverInfo.name={name!r})"


def wait_for_bees_server(base_url: str, timeout: float = DEFAULT_TIMEOUT, wait: float = 0.0) -> tuple[int, str]:
    """Run check_bees_server, retrying for up to ``wait`` seconds while nothing is listening.

    Only EXIT_NOT_LISTENING is retried (a server that is still starting); any other result returns at once.
    """
    deadline = time.monotonic() + wait
    while True:
        code, reason = check_bees_server(base_url, timeout)
        if code != EXIT_NOT_LISTENING or time.monotonic() >= deadline:
            return code, reason
        time.sleep(POLL_INTERVAL)


def _validate_base_url(base_url: str) -> None:
    """Raise ValueError unless base_url is an http:// or https:// URL with a host and a port from 1 to 65535.

    The port must be explicit: an empty port variable would otherwise yield a URL that silently checks port 80.
    """
    try:
        parts = urllib.parse.urlsplit(base_url)
    except ValueError as exc:  # e.g. an unclosed IPv6 bracket
        raise ValueError(f"URL is malformed ({exc}), got {base_url!r}") from None
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"URL must start with http:// or https://, got {base_url!r}")
    if not parts.hostname:
        raise ValueError(f"URL has no host, got {base_url!r}")
    bad_port = f"URL port must be a number from 1 to 65535, got {base_url!r}"
    try:
        port = parts.port  # raises ValueError for a non-numeric or out-of-range port
    except ValueError:
        raise ValueError(bad_port) from None
    if port is None:
        raise ValueError(f"URL must include a port, e.g. http://127.0.0.1:8473, got {base_url!r}")
    if port == 0:
        raise ValueError(bad_port)


class _ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser whose usage errors exit with EXIT_USAGE instead of 2 (which means 'not bees')."""

    def error(self, message: str):
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description="Check that the server at a base URL is a bees MCP server.")
    parser.add_argument("url", nargs="?", help="base URL of the server, e.g. http://127.0.0.1:8473")
    parser.add_argument("--url", dest="url_option", metavar="URL", help="base URL (alternative to the positional)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"per-request timeout in seconds (default {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=0.0,
        help="keep retrying for up to this many seconds while nothing is listening (default 0)",
    )
    args = parser.parse_args(argv)

    # Bad values must exit EXIT_USAGE: an uncaught error would exit 1, which reads as "nothing listening".
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error(f"--timeout must be a finite number of seconds greater than 0, got {args.timeout}")
    if not math.isfinite(args.wait) or args.wait < 0:
        parser.error(f"--wait must be a finite number of seconds, 0 or greater, got {args.wait}")
    base_url = args.url_option or args.url
    if not base_url:
        parser.error("a base URL is required (positional or --url)")
    try:
        _validate_base_url(base_url)
    except ValueError as exc:
        parser.error(str(exc))

    code, reason = wait_for_bees_server(base_url, args.timeout, args.wait)
    print(reason, file=sys.stdout if code == EXIT_BEES else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
