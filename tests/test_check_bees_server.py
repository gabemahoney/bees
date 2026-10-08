"""
Tests for the CI pre-flight identity check (docker/check_bees_server.py) and the
CI bees server bind host (docker/ci_bind_host.py).

PURPOSE:
The /ci pre-flight must confirm that the HTTP server on the CI port really is
bees, not just any service that answers /health, at the address the CI
containers reach. These tests run the check against in-process stub HTTP
servers on OS-assigned ports.

SCOPE - Tests that belong here:
- parse_server_name over plain JSON and SSE initialize responses
- check_bees_server exit codes: bees (0), nothing listening (1), not bees (2),
  including how connection failures split between 1 and 2
- the expected server name matches the real bees MCP server
- MCP session cleanup (DELETE with the session header)
- wait_for_bees_server retry policy (retries only while nothing listens)
- main() argument handling and exit codes, including usage errors (3)
- ci_bind_host: the bind host chosen from `docker network inspect bridge` output
  (the bridge gateway if it is a host address, else 127.0.0.1, never 0.0.0.0)
  and the host-address test, also where any address can be bound
- CI scripts use one configurable port and the identity check, not /health,
  at the bind host and from a container
- the /ci skill stops the bees server a /ci run started, and only that one, when the run ends,
  and launches each phase as its own command
- CI files work on any machine: no machine-specific paths; run_test.sh passes the host's bugs
  hive and repo root into the container, runs the test plan of this checkout, shows bees' output
  when `bees list-hives` fails, and mounts host Claude config files only if they exist; the image
  has what file_bug.py imports
- the /ci skill gives every phase a deadline, and polls for lines the CI scripts really print

SCOPE - Tests that DON'T belong here:
- bees serve flags and HTTP routes -> test_cli_serve.py
- bugs hive choice and file_bug.py behavior -> test_ci_bug_filing.py
- how /ci reads the test plan and records phase statuses (ci_plan.py) -> test_ci_skill.py
"""

import errno
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.mcp_server import mcp
from tests.helpers import load_script, mcp_initialize_response

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "docker" / "check_bees_server.py"
BIND_HOST_SCRIPT = REPO_ROOT / "docker" / "ci_bind_host.py"
CI_SKILL = REPO_ROOT / ".claude" / "skills" / "ci" / "SKILL.md"

cbs = load_script(SCRIPT)
cbh = load_script(BIND_HOST_SCRIPT)

# Linux routes all of 127.0.0.0/8 to loopback, so 127.0.0.2 can stand in for a local bridge gateway,
# and IP_FREEBIND lets a test socket bind an address of another host.
_LINUX_ONLY = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")


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
        message = mcp_initialize_response(name, request["id"])
        out_headers = {"mcp-session-id": session_id} if session_id else {}
        if sse:
            out_headers["Content-Type"] = "text/event-stream"
            return 200, out_headers, f"event: message\r\ndata: {message}\r\n\r\n".encode()
        out_headers["Content-Type"] = "application/json"
        return 200, out_headers, message.encode()

    return respond


# A service that is healthy on /health but has no /mcp endpoint (404).
_HEALTH_ONLY = {("GET", "/health"): (200, {"Content-Type": "application/json"}, b'{"status":"OK"}')}


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

_BEES_INIT = mcp_initialize_response("bees")

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
# ci_bind_host
# ---------------------------------------------------------------------------


def _bridge_inspect(*gateways):
    """`docker network inspect bridge` output with one IPAM config per gateway (None: no Gateway key)."""
    configs = [{"Subnet": "172.17.0.0/16", **({"Gateway": g} if g else {})} for g in gateways]
    return json.dumps([{"Name": "bridge", "IPAM": {"Driver": "default", "Config": configs or None}}])


@pytest.mark.parametrize(
    "inspect_output, local_addresses, expected",
    [
        pytest.param(_bridge_inspect("172.17.0.1"), {"172.17.0.1"}, "172.17.0.1", id="linux_docker_engine"),
        # Docker Desktop: the bridge lives in a VM and host.docker.internal leads to the host's loopback.
        pytest.param(_bridge_inspect("172.17.0.1"), set(), "127.0.0.1", id="gateway_not_a_host_address"),
        pytest.param(_bridge_inspect("fd00::1", "172.18.0.1"), {"fd00::1", "172.18.0.1"}, "172.18.0.1", id="ipv6_skip"),
        pytest.param(_bridge_inspect("172.17.0.1/16"), {"172.17.0.1"}, "172.17.0.1", id="gateway_with_prefix"),
        pytest.param(_bridge_inspect(None), set(), "127.0.0.1", id="no_gateway"),
        pytest.param(_bridge_inspect(), set(), "127.0.0.1", id="null_ipam_config"),
        pytest.param("Error: network bridge not found", set(), "127.0.0.1", id="unreadable_output"),
        # Never the wildcard (exposes the server on every network) or a non-unicast address, even if bindable.
        pytest.param(_bridge_inspect("0.0.0.0"), {"0.0.0.0"}, "127.0.0.1", id="wildcard_gateway"),
        pytest.param(_bridge_inspect("255.255.255.255"), {"255.255.255.255"}, "127.0.0.1", id="broadcast_gateway"),
    ],
)
def test_bind_host_is_bridge_gateway_only_if_host_address(monkeypatch, inspect_output, local_addresses, expected):
    monkeypatch.setattr(
        cbh,
        "local_address_error",
        lambda address: None if address in local_addresses else "Cannot assign requested address",
    )

    bind_host, reason = cbh.choose_bind_host(cbh.bridge_gateways(inspect_output))

    assert bind_host == expected, reason


@pytest.mark.parametrize(
    "stdin, expected",
    [
        pytest.param(_bridge_inspect("127.0.0.2"), "127.0.0.2", marks=_LINUX_ONLY, id="gateway_is_host_address"),
        pytest.param(_bridge_inspect("192.0.2.1"), "127.0.0.1", id="gateway_not_host_address"),  # TEST-NET-1
        pytest.param("", "127.0.0.1", id="docker_inspect_failed"),
    ],
)
def test_bind_host_script_prints_only_the_host_and_exits_0(stdin, expected):
    """run_test.sh runs it under `set -e` and uses all of its stdout as the bind host."""
    result = subprocess.run(
        [sys.executable, str(BIND_HOST_SCRIPT)], input=stdin, capture_output=True, text=True, timeout=30
    )

    assert (result.returncode, result.stdout) == (0, f"{expected}\n"), result.stderr


@pytest.fixture
def nonlocal_bind(request, monkeypatch):
    """If the param is true, ci_bind_host's sockets bind any address, as with net.ipv4.ip_nonlocal_bind=1."""
    if not request.param:
        return
    ip_freebind = 15  # Linux <linux/in.h>; the socket module names it only from Python 3.12

    class FreebindSocket(socket.socket):
        def bind(self, address):
            self.setsockopt(socket.SOL_IP, ip_freebind, 1)
            super().bind(address)

    try:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_IP, ip_freebind, 1)
    except OSError as exc:
        pytest.skip(f"cannot set IP_FREEBIND: {exc}")
    monkeypatch.setattr(cbh, "socket", SimpleNamespace(**{**vars(socket), "socket": FreebindSocket}))


@pytest.mark.parametrize(
    "nonlocal_bind, address, is_local",
    [
        pytest.param(False, "127.0.0.1", True, id="loopback"),
        pytest.param(True, "127.0.0.1", True, marks=_LINUX_ONLY, id="loopback_any_address_binds"),
        # Regression b.y8v: where any address binds, a bind-only check took a remote gateway for a host address.
        pytest.param(True, "192.0.2.1", False, marks=_LINUX_ONLY, id="remote_address_binds"),  # TEST-NET-1
    ],
    indirect=["nonlocal_bind"],
)
def test_local_address_error_accepts_only_host_addresses(nonlocal_bind, address, is_local):
    start = time.monotonic()

    error = cbh.local_address_error(address)

    assert (error is None) == is_local, error
    assert time.monotonic() - start < 2, "a remote address must not stall the CI pre-flight"


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


def _run_test_commands():
    """docker/run_test.sh, one command per line: backslash-continued lines are joined."""
    return (REPO_ROOT / "docker" / "run_test.sh").read_text().replace("\\\n", " ").splitlines()


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
def test_ci_preflight_checks_identity_at_bind_host(path):
    """Regressions b.9jp (/health passed any service) and b.y8v (containers cannot reach loopback on Linux)."""
    text = (REPO_ROOT / path).read_text()
    check_hosts = re.findall(r'check_bees_server\.py[^\n]*?"https?://([^:/"]+)', text)
    serve_commands = re.findall(r"bees serve --http\b[^\n]*", text)
    serve_hosts = [re.search(r"--host\s+(\S+)", command) for command in serve_commands]

    assert "check_bees_server.py" in text
    assert not re.search(r"curl[^\n]*/health", text)
    assert check_hosts and serve_commands
    assert all(serve_hosts), f"bees serve without --host: {serve_commands}"
    fixed_hosts = {"127.0.0.1", "localhost", "0.0.0.0"} & {*check_hosts, *(m[1] for m in serve_hosts)}
    assert not fixed_hosts, f"use the bind host, not {sorted(fixed_hosts)}"
    assert "ci_bind_host.py" in text


def test_run_test_checks_bees_from_a_container_before_the_phase():
    """Regression b.y8v: the host-side check can pass while the containers reach another service, or nothing."""
    commands = _run_test_commands()
    dockerfile = (REPO_ROOT / "docker" / "Dockerfile.test").read_text()
    copied_to = re.search(r"^COPY docker/check_bees_server\.py (\S+)", dockerfile, re.M)

    def lines_starting(prefix):
        return [i for i, command in enumerate(commands) if command.startswith(prefix)]

    # Unindented, so it always runs: also when BEES_MCP_URL is set.
    probes = [i for i in lines_starting("_docker run --rm") if "check_bees_server.py" in commands[i]]
    [build], [phase] = lines_starting("_docker build"), lines_starting("_docker run -d")

    assert copied_to, "Dockerfile.test must copy check_bees_server.py into the image"
    assert len(probes) == 1, "run_test.sh must run check_bees_server.py in a container"
    assert build < probes[0] < phase
    assert f'{copied_to[1]} "${{BEES_MCP_URL}}"' in commands[probes[0]]
    # A failed probe stops the script before the phase starts.
    assert not re.search(r"\|\|\s*(true|:)\s*$", commands[probes[0]]), "the probe's exit status must not be swallowed"
    assert any(re.fullmatch(r"\s*exit [1-9]\d*", command) for command in commands[probes[0] + 1 : phase])
    # The probe sees the host the way the phase container does: one shared --add-host mapping.
    assert all('"${ADD_HOST_ARGS[@]}"' in commands[i] for i in (probes[0], phase))
    assert sum(command.count("--add-host") for command in commands) == 1


def _skill_section(heading_prefix):
    """(heading, body) of the first /ci skill section whose heading starts with ``heading_prefix`` (None if none).

    The body runs to the next heading. A `#` line inside a code block (a bash comment) is not a heading.
    """
    sections, in_code = [], False
    for line in CI_SKILL.read_text().splitlines(keepends=True):
        in_code ^= line.lstrip().startswith("```")
        heading = not in_code and re.match(r"#+ (.*)", line)
        if heading:
            sections.append((heading[1], []))
        elif sections:
            sections[-1][1].append(line)
    return next(((heading, "".join(body)) for heading, body in sections if heading.startswith(heading_prefix)), None)


def _bash_blocks(markdown):
    return re.findall(r"```bash\n(.*?)```", markdown, re.S)


def _bash_lines(markdown):
    return [line.strip() for block in _bash_blocks(markdown) for line in block.splitlines()]


def _ci_server_pid_file():
    """The file the command that starts the CI bees server records its PID in (None if it records none)."""
    [start] = [command for command in _bash_lines(CI_SKILL.read_text()) if command.startswith("bees serve")]
    pid_file = re.search(r"echo \$! > (\S+)$", start)
    return pid_file and pid_file[1]


def _ps_guard(markdown, pid_file, action):
    """Text from a `ps -p` look at the recorded PID's command line to the next ``action`` line (None if none)."""
    guard = re.search(rf"ps -p\b[^\n]*{re.escape(pid_file)}[^\n]*args=(.*?)^\s*{action}", markdown, re.M | re.S)
    return guard and guard[1]


def test_ci_skill_kills_only_the_bees_server_it_started():
    """Regression b.y8v: the server /ci starts has no auth and every container reaches it, so /ci stops it."""
    skill_commands = _bash_lines(CI_SKILL.read_text())
    pid_file = _ci_server_pid_file()
    stop = _skill_section("Stop the bees server")
    kills = [command for command in skill_commands if re.match(r"(kill|pkill|killall)\b", command)]

    assert pid_file, "the command that starts bees must record the server's PID"
    assert stop, "the skill must say how to stop the bees server it started"
    # Guard: kill the recorded PID only if its command line is still that bees server (the PID may be reused).
    guard = _ps_guard(stop[1], pid_file, r"kill\s")
    assert guard and "bees serve" in guard
    assert kills and kills == [c for c in _bash_lines(stop[1]) if c.startswith("kill")], "every kill must be guarded"


def test_ci_skill_keeps_the_pid_record_of_a_server_an_interrupted_run_started():
    """Regression b.y8v: deleting the record whenever bees already runs left an interrupted run's server up for good."""
    pid_file = _ci_server_pid_file()

    # Delete the record only after `ps` shows the recorded PID is not the bees server a /ci run started.
    guard = _ps_guard(_skill_section("Step 1")[1], pid_file, rf"rm\b[^\n]*{re.escape(pid_file)}")
    assert guard and "bees serve" in guard


def test_ci_skill_launches_each_phase_in_its_own_command():
    """Regression b.y8v: one command running several launches reports only the last launch's exit status."""
    launches = [block.count("run_test.sh") for block in _bash_blocks(CI_SKILL.read_text())]

    assert {count for count in launches if count} == {1}


@pytest.mark.parametrize("section", ["Step 2", "Phase 1", "Remaining phases", "Launch failure", "Step 5"])
def test_ci_skill_stops_the_bees_server_when_the_run_ends(section):
    """Regression b.y8v: a run that ends without stopping it leaves an unauthenticated server on the bridge address."""
    stop_heading = _skill_section("Stop the bees server")[0]
    run_end = _skill_section(section)

    assert run_end, f"no section starting {section!r}"
    assert stop_heading.lower() in run_end[1].lower()


# ---------------------------------------------------------------------------
# CI bug filing and phase deadline (static regression checks)
# ---------------------------------------------------------------------------

# The CI scripts and the skills that drive them: they must run unmodified on any machine.
_PORTABLE_CI_FILES = [
    *sorted(path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / "docker").iterdir() if path.is_file()),
    *(f".claude/skills/{skill}/SKILL.md" for skill in ("ci", "file-bug-http", "release-test", "publish")),
    "tests/integration.sh",
]
# A user's home directory or a Homebrew prefix. /home/testuser is the CI container's own user.
_MACHINE_SPECIFIC_PATH = re.compile(r"/(?:home/(?!testuser\b)|Users/)[\w.-]+|/opt/homebrew\b")


def test_ci_files_have_no_machine_specific_paths():
    """Regression b.g76: file_bug.py had one developer's repo root built in, the publish skill their pipx path."""
    found = {path: _MACHINE_SPECIFIC_PATH.findall((REPO_ROOT / path).read_text()) for path in _PORTABLE_CI_FILES}

    assert {path: hits for path, hits in found.items() if hits} == {}


def test_run_test_passes_the_hosts_bugs_hive_and_repo_root_into_the_container():
    """Regression b.g76: the containers filed bugs into a hive and repo root built into file_bug.py."""
    commands = _run_test_commands()
    [phase] = [command for command in commands if command.startswith("_docker run -d")]
    [build] = [i for i, command in enumerate(commands) if command.startswith("_docker build")]
    [pick] = [i for i, c in enumerate(commands) if "ci_bugs_hive.py" in c and not c.lstrip().startswith("#")]
    pick_end = next(i for i in range(pick, len(commands)) if commands[i].strip() == "fi")

    assert all(f'-e "{var}=${{{var}}}"' in phase for var in ("BEES_BUGS_HIVE", "BEES_REPO_ROOT"))
    # With no bugs hive found, the script stops before the build: no phase runs without one.
    assert pick < build
    assert any(re.fullmatch(r"\s*exit [1-9]\d*", command) for command in commands[pick:pick_end])


def test_run_test_runs_the_test_plan_of_this_checkout():
    """Regression b.g76: run_test.sh mounted the host's hive named testplans: maybe another checkout's or repo's."""
    commands = _run_test_commands()
    [phase] = [command for command in commands if command.startswith("_docker run -d")]
    mount = re.search(r'-v "\$\{(\w+)\}:/tmp/testplans_host:ro"', phase)
    [plan] = [m[1] for command in commands if (m := re.fullmatch(r'TEST_PLAN_ID="([^"]+)"', command))]
    unset_hive = commands.index('if [[ -z "${BEES_BUGS_HIVE:-}" ]]; then')
    unset_hive_end = commands.index("fi", unset_hive)
    list_hives = [i for i, c in enumerate(commands) if "bees list-hives" in c and not re.match(r"\s*(#|echo\b)", c)]

    assert mount, "the phase container must get the testplans hive"
    assert [c for c in commands if c.startswith(f"{mount[1]}=")] == [f'{mount[1]}="${{PROJECT_ROOT}}/docker/testplans"']
    assert (REPO_ROOT / "docker" / "testplans" / plan / f"{plan}.md").is_file()
    # The host's hives serve only to find the bugs hive, so they are listed only when BEES_BUGS_HIVE is not set.
    assert list_hives and all(unset_hive < i < unset_hive_end for i in list_hives)


def test_run_test_shows_what_bees_said_when_list_hives_fails():
    """bees reports its errors (e.g. a config conflict) as JSON on stdout: without it the stop says not why."""
    commands = _run_test_commands()
    [listing] = [i for i, command in enumerate(commands) if re.search(r"HIVES_JSON=\$\(.*bees list-hives", command)]
    stop = next(i for i in range(listing, len(commands)) if re.fullmatch(r"\s*exit [1-9]\d*", commands[i]))

    assert commands[listing].lstrip().startswith("if ! "), "the failure branch must follow the listing"
    assert any(re.match(r"\s*echo\b.*\$\{HIVES_JSON\}", command) for command in commands[listing + 1 : stop])


def test_run_test_mounts_host_claude_config_files_only_if_they_exist():
    """Regression b.g76: for a missing ~/.claude.json, docker run made a root-owned directory at that path."""
    commands = _run_test_commands()
    [phase] = [command for command in commands if command.startswith("_docker run -d")]
    mounts = [(i, m) for i, c in enumerate(commands) if (m := re.search(r'(\w+)\+=\(-v "([^":]+):/host-claude', c))]
    arrays = {mount[1] for _, mount in mounts}

    assert len(mounts) == 2 and len(arrays) == 1, "~/.claude.json and ~/.claude/settings.json, added to one array"
    assert all(commands[i - 1].strip() == f'if [[ -f "{mount[2]}" ]]; then' for i, mount in mounts)
    assert "/host-claude" not in phase
    # The array may be empty: expanded in the form that set -u accepts on bash before 4.4 too (macOS ships 3.2).
    [array] = arrays
    assert f'${{{array}[@]+"${{{array}[@]}}"}}' in phase


def test_dockerfile_installs_file_bugs_imports_next_to_it():
    """file_bug.py imports its docker/ neighbours, which Python finds only in the script's own directory."""
    file_bug = REPO_ROOT / "docker" / "file_bug.py"
    dockerfile = (REPO_ROOT / "docker" / "Dockerfile.test").read_text()
    copies = re.findall(r"^COPY docker/(\S+) (\S+)$", dockerfile, re.M)
    installed = {source: Path(target).parent for source, target in copies}
    imported = re.findall(r"^(?:from|import) (\w+)", file_bug.read_text(), re.M)
    neighbours = [f"{name}.py" for name in imported if (file_bug.parent / f"{name}.py").is_file()]

    assert neighbours, "file_bug.py must share the bugs hive rule with run_test.sh (ci_bugs_hive.py)"
    assert {name: installed.get(name) for name in neighbours} == dict.fromkeys(neighbours, installed["file_bug.py"])


def test_ci_skill_times_out_a_phase_that_never_reports():
    """Regression b.g76: /ci waited forever for a phase that never printed a result, e.g. after a failed filing."""
    timeout = re.search(
        r"\$\{BEES_CI_PHASE_TIMEOUT_MINUTES:-([1-9]\d*)\}", "\n".join(_bash_lines(_skill_section("Step 1")[1]))
    )
    polls = [
        block
        for section in ("Phase 1", "Remaining phases")
        for block in _bash_blocks(_skill_section(section)[1])
        if "tmux capture-pane" in block
    ]

    assert timeout, "Step 1 must resolve the phase timeout, with a default of at least one minute"
    assert len(polls) == 2 and all("date +%s" in poll for poll in polls), "every poll must check the phase deadline"
    assert "deadline" in _skill_section("Monitor signals")[1]


def test_ci_skill_monitor_signals_are_lines_the_ci_scripts_print():
    """A signal that nothing prints never shows up: /ci would see the phase only at its deadline."""
    signals = re.findall(r"^- \*\*`([^`]+)`\*\*", _skill_section("Monitor signals")[1], re.M)
    output_lines = [
        line
        for path in ("tests/integration.sh", "docker/entrypoint.sh", "docker/run_test.sh", "docker/file_bug.py")
        for line in (REPO_ROOT / path).read_text().splitlines()
        if re.search(r"\b(echo|print)\b", line) and not line.lstrip().startswith("#")
    ]

    def printed(signal):
        # N stands for the phase number: a number or a shell variable in the scripts.
        pattern = r"(?:\d+|\$\{?\w+\}?)".join(re.escape(part) for part in re.split(r"\bN\b", signal))
        return any(re.search(pattern, line) for line in output_lines)

    assert {"BUG FILED:", "BUG FILING FAILED:", "TEST RUNNER EXITED"} <= set(signals)
    assert [signal for signal in signals if not printed(signal)] == []
