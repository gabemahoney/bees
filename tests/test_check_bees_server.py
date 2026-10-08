"""
Tests for the CI pre-flight identity check (docker/check_bees_server.py).

PURPOSE:
The /ci pre-flight must confirm that the HTTP server on the CI port really is
bees, not just any service that answers /health. These tests run the check
against in-process stub HTTP servers on OS-assigned ports.

SCOPE - Tests that belong here:
- parse_server_name over plain JSON and SSE initialize responses
- check_bees_server exit codes: bees (0), nothing listening (1), not bees (2),
  including how connection failures split between 1 and 2
- the expected server name matches the real bees MCP server
- MCP session cleanup (DELETE with the session header)
- wait_for_bees_server retry policy (retries only while nothing listens)
- main() argument handling and exit codes, including usage errors (3)
- CI scripts use one configurable port and the identity check, not /health

SCOPE - Tests that DON'T belong here:
- bees serve flags and HTTP routes -> test_cli_serve.py
"""

import errno
import importlib.util
import json
import re
import socket
import ssl
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.mcp_server import mcp

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "docker" / "check_bees_server.py"

# docker/ is not a package, so load the script by path.
_spec = importlib.util.spec_from_file_location("check_bees_server", SCRIPT)
cbs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cbs)


def _initialize_response(name: str, request_id: int = 1) -> str:
    """JSON-RPC initialize result for an MCP server called ``name``."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "serverInfo": {"name": name, "version": "1.0"},
            },
        }
    )


def _bees_like(name="bees", sse=False, session_id=None):
    """Responder that answers initialize like an MCP streamable-HTTP server (406/415/400 on bad requests)."""

    def respond(headers, body):
        accept = headers.get("accept", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            return 406, {}, b"Not Acceptable"
        if not headers.get("content-type", "").startswith("application/json"):
            return 415, {}, b"Unsupported Media Type"
        request = json.loads(body)
        if request.get("method") != "initialize":
            return 400, {}, b"Bad Request"
        message = _initialize_response(name, request["id"])
        out_headers = {"mcp-session-id": session_id} if session_id else {}
        if sse:
            out_headers["Content-Type"] = "text/event-stream"
            return 200, out_headers, f"event: message\r\ndata: {message}\r\n\r\n".encode()
        out_headers["Content-Type"] = "application/json"
        return 200, out_headers, message.encode()

    return respond


# A service that is healthy on /health but has no /mcp endpoint (404).
_HEALTH_ONLY = {("GET", "/health"): (200, {"Content-Type": "application/json"}, b'{"status":"OK"}')}


class _StubHandler(BaseHTTPRequestHandler):
    """Answers from server.routes: {(method, path): (status, headers, body) | responder | None (drop)}."""

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        headers = {key.lower(): value for key, value in self.headers.items()}
        self.server.requests.append(SimpleNamespace(method=self.command, path=self.path, headers=headers))
        route = self.server.routes.get((self.command, self.path), (404, {}, b"Not Found"))
        if route is None:
            self.close_connection = True  # accept the request, then hang up without a response
            return
        status, out_headers, payload = route(headers, body) if callable(route) else route
        self.send_response(status)
        for key, value in out_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_DELETE = _handle

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_server():
    """Factory: start a stub HTTP server on 127.0.0.1 with an OS-assigned port; returns it with .url."""
    servers = []

    def start(routes):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        server.routes = routes
        server.requests = []
        server.url = f"http://127.0.0.1:{server.server_address[1]}"
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def closed_port_url():
    """Base URL of an OS-assigned 127.0.0.1 port that was just released, so nothing listens on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def fake_clock(monkeypatch):
    """Replace the script's time module with a clock that only advances when sleep() is called."""
    clock = SimpleNamespace(now=0.0)
    clock.monotonic = lambda: clock.now

    def sleep(seconds):
        clock.now += seconds

    clock.sleep = sleep
    monkeypatch.setattr(cbs, "time", clock)
    return clock


# ---------------------------------------------------------------------------
# parse_server_name
# ---------------------------------------------------------------------------

_BEES_INIT = _initialize_response("bees")

# Unescaped U+2028, U+2029 and U+0085 are valid inside a JSON string but are not SSE line breaks.
_BEES_INIT_UNICODE_BREAKS = json.dumps(
    {"result": {"serverInfo": {"name": "bees", "title": "a\u2028b\u2029c\u0085d"}}}, ensure_ascii=False
)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(_BEES_INIT, id="plain_json"),
        pytest.param(f"event: message\r\ndata: {_BEES_INIT}\r\n\r\n", id="sse_crlf"),
        pytest.param(
            ': ping\n\nevent: ping\ndata: \n\ndata: {"jsonrpc": "2.0", "method": "notifications/message"}\n\n'
            f"event: message\ndata: {_BEES_INIT}\n\n",
            id="sse_result_after_pings_and_notification",
        ),
        pytest.param(
            'event: message\ndata:{"jsonrpc": "2.0", "id": 1,\ndata: "result": {"serverInfo": {"name": "bees"}}}',
            id="sse_multiline_data_without_final_blank_line",
        ),
        # Regression b.9jp: str.splitlines() split the data line at these characters, so the JSON never parsed.
        pytest.param(f"event: message\ndata: {_BEES_INIT_UNICODE_BREAKS}\n\n", id="sse_unescaped_unicode_line_breaks"),
    ],
)
def test_parse_server_name_reads_initialize_result(body):
    assert cbs.parse_server_name(body) == "bees"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("<html><body>Not Found</body></html>", id="html"),
        pytest.param("[1, 2]", id="json_list"),
        pytest.param('{"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "x"}}', id="jsonrpc_error"),
    ],
)
def test_parse_server_name_rejects_non_initialize_bodies(body):
    with pytest.raises(ValueError):
        cbs.parse_server_name(body)


# ---------------------------------------------------------------------------
# check_bees_server
# ---------------------------------------------------------------------------


def test_expected_server_name_is_the_real_bees_server_name():
    """Renaming the bees MCP server without updating the check would make CI reject the real bees server."""
    assert mcp.name == cbs.EXPECTED_SERVER_NAME


@pytest.mark.parametrize(
    "routes, url_suffix, expected",
    [
        pytest.param({("POST", "/mcp"): _bees_like()}, "", 0, id="bees_json"),
        pytest.param({("POST", "/mcp"): _bees_like(sse=True)}, "", 0, id="bees_sse"),
        pytest.param({("POST", "/mcp"): _bees_like(sse=True)}, "/", 0, id="bees_trailing_slash_base_url"),
        # Regression b.9jp: the old `curl -sf <base>/health` pre-flight accepted this service as bees.
        pytest.param(_HEALTH_ONLY, "", 2, id="health_only_404"),
        pytest.param({**_HEALTH_ONLY, ("POST", "/mcp"): (405, {}, b"")}, "", 2, id="mcp_method_not_allowed"),
        pytest.param(
            {**_HEALTH_ONLY, ("POST", "/mcp"): (200, {}, b'{"status":"OK"}')}, "", 2, id="mcp_answers_health_json"
        ),
        pytest.param({("POST", "/mcp"): _bees_like(name="other-server")}, "", 2, id="other_mcp_server_json"),
        pytest.param({("POST", "/mcp"): _bees_like(name="other-server", sse=True)}, "", 2, id="other_mcp_server_sse"),
        pytest.param({("POST", "/mcp"): None}, "", 2, id="drops_connection_without_response"),
    ],
)
def test_check_bees_server_classifies_responder(stub_server, routes, url_suffix, expected):
    server = stub_server(routes)

    code, reason = cbs.check_bees_server(server.url + url_suffix, timeout=2)

    assert code == expected, reason
    assert (server.requests[0].method, server.requests[0].path) == ("POST", "/mcp")


def test_check_bees_server_nothing_listening(closed_port_url):
    code, _ = cbs.check_bees_server(closed_port_url, timeout=2)

    assert code == 1


def test_check_bees_server_connected_but_silent_is_not_bees():
    """A listener that accepts the connection but never answers times out as 'not bees', not 'not listening'."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)  # the kernel completes the handshake; nothing ever reads or replies
        code, _ = cbs.check_bees_server(f"http://127.0.0.1:{sock.getsockname()[1]}", timeout=0.2)

    assert code == 2


def test_check_bees_server_https_against_plain_http_is_not_bees(stub_server):
    """The TLS handshake fails after the connection is accepted, so a server holds the port: not bees, not 1."""
    server = stub_server({("POST", "/mcp"): _bees_like()})

    code, reason = cbs.check_bees_server(server.url.replace("http://", "https://", 1), timeout=2)

    assert code == 2, reason


@pytest.mark.parametrize(
    "reason, expected",
    [
        pytest.param(ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused"), 1, id="refused"),
        pytest.param(OSError(errno.EHOSTUNREACH, "No route to host"), 1, id="host_unreachable"),
        pytest.param(socket.gaierror(socket.EAI_NONAME, "Name or service not known"), 1, id="host_not_resolved"),
        pytest.param(ConnectionResetError(errno.ECONNRESET, "Connection reset by peer"), 2, id="reset"),
        pytest.param(TimeoutError("timed out"), 2, id="timeout"),
        pytest.param(ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number"), 2, id="tls_failure"),
        pytest.param("no host given", 2, id="string_reason"),
    ],
)
def test_check_bees_server_classifies_connection_failure(monkeypatch, reason, expected):
    """Only a refused, unreachable or unresolved host means nothing is listening; other failures mean not bees."""

    def fail(request, timeout):
        raise urllib.error.URLError(reason)

    monkeypatch.setattr(cbs, "_OPENER", SimpleNamespace(open=fail))

    code, _ = cbs.check_bees_server("http://bees.test:8473", timeout=2)

    assert code == expected


@pytest.mark.parametrize(
    "session_id, delete_status, expected_deletes",
    [
        pytest.param(None, 200, [], id="no_session_no_delete"),
        pytest.param("abc123", 200, [("/mcp", "abc123")], id="session_closed"),
        pytest.param("abc123", 404, [("/mcp", "abc123")], id="delete_failure_ignored"),
    ],
)
def test_check_bees_server_closes_mcp_session(stub_server, session_id, delete_status, expected_deletes):
    server = stub_server(
        {
            ("POST", "/mcp"): _bees_like(sse=True, session_id=session_id),
            ("DELETE", "/mcp"): (delete_status, {}, b""),
        }
    )

    code, _ = cbs.check_bees_server(server.url, timeout=2)

    assert code == 0
    deletes = [(r.path, r.headers.get("mcp-session-id")) for r in server.requests if r.method == "DELETE"]
    assert deletes == expected_deletes


# ---------------------------------------------------------------------------
# wait_for_bees_server
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "results, wait, expected_code, expected_calls",
    [
        pytest.param([1, 1, 0], 60, 0, 3, id="retries_until_bees"),
        pytest.param([1, 2], 60, 2, 2, id="retries_until_something_answers"),
        pytest.param([2, 0], 60, 2, 1, id="no_retry_when_not_bees"),
        pytest.param([0, 0], 60, 0, 1, id="no_retry_when_bees"),
        pytest.param([1, 0], 0, 1, 1, id="no_wait_single_attempt"),
        pytest.param([1] * 10, 1.2, 1, 4, id="gives_up_at_deadline"),
    ],
)
def test_wait_for_bees_server_retries_only_while_nothing_listens(
    monkeypatch, fake_clock, results, wait, expected_code, expected_calls
):
    outcomes = iter(results)
    calls = []

    def fake_check(base_url, timeout=cbs.DEFAULT_TIMEOUT):
        calls.append(base_url)
        code = next(outcomes)
        return code, f"result {code}"

    monkeypatch.setattr(cbs, "check_bees_server", fake_check)

    code, _ = cbs.wait_for_bees_server("http://bees.test", timeout=2, wait=wait)

    assert code == expected_code
    assert len(calls) == expected_calls


# ---------------------------------------------------------------------------
# main / command line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "routes, use_url_option, expected",
    [
        pytest.param({("POST", "/mcp"): _bees_like()}, False, 0, id="bees_positional"),
        pytest.param({("POST", "/mcp"): _bees_like(sse=True)}, True, 0, id="bees_url_option"),
        pytest.param(_HEALTH_ONLY, False, 2, id="health_only_impostor"),
    ],
)
def test_main_exit_code_matches_server(stub_server, capsys, routes, use_url_option, expected):
    url = stub_server(routes).url
    argv = ["--timeout", "2", "--url", url] if use_url_option else ["--timeout", "2", url]

    assert cbs.main(argv) == expected
    out, err = capsys.readouterr()
    assert (out if expected == 0 else err).strip()


def test_main_wait_option_retries_until_deadline(fake_clock, closed_port_url):
    assert cbs.main(["--wait", "1.2", closed_port_url]) == 1
    assert 1.2 <= fake_clock.now < 1.2 + cbs.POLL_INTERVAL


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no_url"),
        pytest.param(["bees.test:8473"], id="missing_scheme"),
        pytest.param(["http://[::1"], id="malformed_url"),
        pytest.param(["http://:8473"], id="no_host"),
        pytest.param(["http://bees.test:"], id="empty_port"),
        pytest.param(["http://bees.test:0"], id="port_zero"),
        pytest.param(["--url", "http://bees.test:70000"], id="port_out_of_range"),
        pytest.param(["--timeout", "0", "http://bees.test:8473"], id="timeout_zero"),
        pytest.param(["--timeout", "nan", "http://bees.test:8473"], id="timeout_not_finite"),
        pytest.param(["--wait", "inf", "http://bees.test:8473"], id="wait_not_finite"),
        pytest.param(["--bogus", "http://bees.test:8473"], id="unknown_option"),
    ],
)
def test_main_usage_errors_exit_3(argv):
    with pytest.raises(SystemExit) as exc_info:
        cbs.main(argv)

    assert exc_info.value.code == 3


def test_script_exit_status_from_command_line(stub_server):
    server = stub_server(_HEALTH_ONLY)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--timeout", "2", server.url], capture_output=True, text=True, timeout=30
    )

    assert result.returncode == 2, result.stderr


# ---------------------------------------------------------------------------
# CI scripts (static regression checks)
# ---------------------------------------------------------------------------

_CI_FILES = [
    ".claude/skills/ci/SKILL.md",
    "docker/run_test.sh",
    "docker/test_runner.sh",
    "docker/entrypoint.sh",
    "docker/file_bug.py",
    "tests/integration.sh",
]


def test_ci_files_share_one_default_port_other_than_8000():
    """Regression b.9jp: another service may already be bound to port 8000 on the CI host."""
    texts = {path: (REPO_ROOT / path).read_text() for path in _CI_FILES}
    port_8000 = re.compile(r"(host\.docker\.internal|127\.0\.0\.1|localhost):8000\b")
    default_port = re.compile(r"(?:host\.docker\.internal:|BEES_CI_PORT:-)(\d+)")

    hard_coded_8000 = [path for path, text in texts.items() if port_8000.search(text)]
    default_ports = {port for text in texts.values() for port in default_port.findall(text)}

    assert hard_coded_8000 == []
    assert len(default_ports) == 1, f"CI files disagree on the default port: {sorted(default_ports)}"


@pytest.mark.parametrize("path", [".claude/skills/ci/SKILL.md", "docker/run_test.sh"])
def test_ci_preflight_checks_identity_not_health(path):
    text = (REPO_ROOT / path).read_text()

    assert "check_bees_server.py" in text
    assert not re.search(r"curl[^\n]*/health", text)
