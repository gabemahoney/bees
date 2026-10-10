"""
Tests for CI bug filing: the bugs hive choice (docker/ci_bugs_hive.py) and the bug filer the CI
containers run (docker/file_bug.py).

PURPOSE:
A failing CI test files a bug into the host's bugs hive for this repo, through the host's bees
server. Hive names and paths differ between machines, so neither is built in: run_test.sh picks
the hive from the host's `bees list-hives` and passes it and the repo root into the container.
bees lists hives of other scopes too (inherited ones, and every scope for a queen repo), so the
choice goes by each hive's scope. Whatever happens, file_bug.py must end in a line /ci polls for
("BUG FILED:" or "BUG FILING FAILED:"), within its time limit, so a failed filing cannot leave
/ci waiting.

file_bug.py runs here against the real bees MCP server, in-process (no network), with its hives
in tmp_path; its time limit, against an in-process stub server on an OS-assigned port.

SCOPE - Tests that belong here:
- choose_bugs_hive: the candidates within a scope, which scope wins, and its scope matching and
  ranking agreeing with bees' own, for any pattern a config may hold (ci_plan.py shares them)
- the ci_bugs_hive.py command line on `bees list-hives` output
- file_bug.py: where the hive and the repo root come from (option, env var, discovery) and the
  ticket it files, with the status it takes from the hive's status values; its copy of bees' hive
  name normalization agreeing with bees'
- file_bug.py failures, including a server that stops answering: each one prints
  "BUG FILING FAILED:" and exits 1

SCOPE - Tests that DON'T belong here:
- how run_test.sh, Dockerfile.test and the /ci skill wire bug filing up -> test_check_bees_server.py
- the bees server identity check -> test_check_bees_server.py
- reading the test plan and the hive /ci records phase statuses through (ci_plan.py) -> test_ci_skill.py
"""

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastmcp.client.transports import FastMCPTransport

from src.config import compute_scope_specificity, match_scope_pattern
from src.id_utils import normalize_hive_name
from src.mcp_hive_ops import write_identity
from src.mcp_server import mcp as bees_mcp
from src.parser import parse_frontmatter
from tests.conftest import write_multi_scope_config, write_queen_repos_config
from tests.helpers import load_script, mcp_initialize_response

DOCKER_DIR = Path(__file__).resolve().parent.parent / "docker"
FILE_BUG = DOCKER_DIR / "file_bug.py"
BUGS_HIVE_SCRIPT = DOCKER_DIR / "ci_bugs_hive.py"

cbh = load_script(BUGS_HIVE_SCRIPT)
fb = load_script(FILE_BUG)

# The repo root the choose_bugs_hive cases list hives for
ROOT = "/repos/bees"


@pytest.fixture(autouse=True)
def no_ci_env(monkeypatch):
    """Clear the env vars the CI container sets, so each test sets only its own."""
    for var in ("BEES_BUGS_HIVE", "BEES_REPO_ROOT", "BUG_SERVER_URL"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def repo_with_hives(isolated_bees_env):
    """Factory: register hives in the scope of the repo root tmp_path, and in ``other_scopes``; returns the root.

    ``other_scopes`` maps scope patterns ({repo} and {parent}: the root and its parent) to hive names.
    ``status_values`` maps "global", "scope" (the root's) or one of ``names`` (None: freeform) to status values.
    """

    def register(*names, other_scopes=None, queen=False, status_values=None):
        levels = status_values or {}
        root = isolated_bees_env.base_path
        hive_names = {str(root): names}
        for pattern, other_names in (other_scopes or {}).items():
            hive_names[pattern.format(repo=root, parent=root.parent)] = other_names
        scopes = {
            pattern: {
                "hives": {
                    name: {"path": str(isolated_bees_env.create_hive(name)), "display_name": name.title()}
                    for name in names_in_scope
                },
                "child_tiers": {},
            }
            for pattern, names_in_scope in hive_names.items()
        }
        if "scope" in levels:
            scopes[str(root)]["status_values"] = levels["scope"]
        write_multi_scope_config(isolated_bees_env.global_bees_dir, scopes)
        if queen:
            write_queen_repos_config(isolated_bees_env.global_bees_dir, [(str(root), None)])
        if "global" in levels:
            config_path = isolated_bees_env.global_bees_dir / "config.json"
            config = json.loads(config_path.read_text())
            config_path.write_text(json.dumps({**config, "status_values": levels["global"]}))
        for name in set(names) & levels.keys():
            marker = root / name / ".hive"
            marker.mkdir()
            identity = {"normalized_name": name, "display_name": name.title(), "status_values": levels[name]}
            write_identity(marker, {**identity, "status_values_explicitly_null": levels[name] is None})
        return root

    return register


@pytest.fixture
def bees_server(monkeypatch):
    """Connect file_bug.py's MCP session to the real bees MCP server in-process, instead of over HTTP."""

    @contextlib.asynccontextmanager
    async def no_http(url):
        yield None, None, None

    monkeypatch.setattr(fb, "streamablehttp_client", no_http)
    monkeypatch.setattr(fb, "ClientSession", lambda read, write: FastMCPTransport(bees_mcp).connect_session())


# How long the hanging server holds each request: far longer than the time limit the test sets.
_HANG_SECONDS = 10


@pytest.fixture
def hanging_mcp_server(stub_server):
    """MCP server that opens a session, then answers nothing: no tool call, no session DELETE; .methods: those asked."""
    release = threading.Event()
    methods = []

    def hang(headers, body):
        release.wait(_HANG_SECONDS)
        return None  # hang up without a response

    def post(headers, body):
        message = json.loads(body)
        methods.append(message.get("method"))
        if message.get("method") == "initialize":
            session = {"Content-Type": "application/json", "mcp-session-id": "ci-session"}
            return 200, session, mcp_initialize_response("bees", message["id"]).encode()
        if "id" not in message:  # a notification: nothing to answer
            return 202, {}, b""
        return hang(headers, body)

    server = stub_server({("POST", "/mcp"): post, ("GET", "/mcp"): hang, ("DELETE", "/mcp"): hang})
    server.methods = methods
    yield server
    release.set()


def _file_bug(monkeypatch, capsys, args, env):
    """Run file_bug.py's main() with ``args`` and ``env`` set; returns (exit code, stdout, stderr)."""
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    argv = ["file_bug.py", "--title", "CI Test 7: list hives", "--description", "Expected 2 hives. Got: 1", *args]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        fb.main()
        code = 0
    except SystemExit as exc:
        code = exc.code
    out, err = capsys.readouterr()
    return code, out, err


def _with_repo(values, repo_root):
    """Replace ``{repo}`` in test parameters with the repo root, known only once the test runs."""
    if isinstance(values, dict):
        return {key: value.format(repo=repo_root) for key, value in values.items()}
    return [value.format(repo=repo_root) for value in values]


# ---------------------------------------------------------------------------
# ci_bugs_hive
# ---------------------------------------------------------------------------


def _hives(scope, *names):
    """list-hives entries for hives ``names``, owned by the scope pattern ``scope``."""
    return [{"normalized_name": n, "display_name": n.title(), "path": f"/hives/{n}", "scope": scope} for n in names]


@pytest.mark.parametrize(
    "hives, expected",
    [
        # Within the repo's own scope
        pytest.param(_hives(ROOT, "bees_bugs", "bugs", "features"), "bugs", id="hive_named_bugs_wins"),
        pytest.param(_hives(ROOT, "bees_bugs", "features"), "bees_bugs", id="only_name_containing_bugs"),
        pytest.param(_hives(ROOT, "bees_bugs", "ci_bugs"), None, id="several_names_containing_bugs"),
        pytest.param(_hives(ROOT, "features", "testplans"), None, id="no_bugs_hive"),
        pytest.param([], None, id="no_hives"),
        pytest.param(
            [{"display_name": "Bugs"}, "bugs", {"normalized_name": "bugs"}, *_hives(None, "bugs")]
            + _hives(ROOT, "ci_bugs"),
            "ci_bugs",
            id="entries_without_name_or_scope_skipped",
        ),
        # Across scopes: the most specific scope for the repo root with a candidate decides
        pytest.param(
            [*_hives("/repos/**", "bugs"), *_hives(ROOT, "bees_bugs")], "bees_bugs", id="own_scope_over_inherited_bugs"
        ),
        pytest.param([*_hives("/**", "bugs"), *_hives(ROOT, "features")], "bugs", id="inherited_scope_if_own_has_none"),
        pytest.param(
            [*_hives("/repos/*", "bugs"), *_hives(f"{ROOT}/**", "team_bugs")], "team_bugs", id="more_segments_first"
        ),
        pytest.param(
            [*_hives("/repos/**", "bugs"), *_hives("/repos/*", "ci_bugs")], "ci_bugs", id="one_level_before_recursive"
        ),
        pytest.param(
            [*_hives("/repos/**", "bugs"), *_hives(ROOT, "bees_bugs", "ci_bugs")],
            None,
            id="several_in_most_specific_scope_no_fallback",
        ),
        pytest.param([*_hives(ROOT, "bugs"), *_hives(f"{ROOT}/", "ci_bugs")], None, id="equally_specific_scopes_tie"),
        # A queen repo's list holds every scope: those that do not match the repo root never count
        pytest.param(
            [*_hives("/elsewhere/repo", "bugs"), *_hives("/repos/other/**", "other_bugs"), *_hives(ROOT, "bees_bugs")],
            "bees_bugs",
            id="queen_repo_other_scopes_ignored",
        ),
        pytest.param([*_hives("/elsewhere/repo", "bugs"), *_hives(ROOT, "features")], None, id="queen_repo_none_here"),
    ],
)
def test_choose_bugs_hive(hives, expected):
    hive, reason = cbh.choose_bugs_hive(hives, ROOT)

    assert hive == expected, reason


def test_choose_bugs_hive_points_at_bugs_hives_of_other_scopes():
    """With no bugs hive for the repo root, the reason names the scopes whose bugs hives it did not use."""
    hive, reason = cbh.choose_bugs_hive([*_hives("/elsewhere/repo", "bugs"), *_hives(ROOT, "features")], ROOT)

    assert hive is None
    assert "/elsewhere/repo" in reason


_SCOPE_ROOTS = [
    "/",
    "/repos",
    "/repos/bees",
    "/repos/bees/sub",
    "/repos/beestwo",
    "/repos/twobees",
    "/repos/bs",
    "/repos/x/bees",
    "/repos/x/y/bees",
    "/repos/x/y/bees/sub",
    "/other/bees",
]


@pytest.mark.parametrize(
    "pattern",
    [
        # What colonize-hive writes: an exact path, a terminal /* or /**
        "/repos/bees",
        "/repos/be",
        "/repos/*",
        "/repos/**",
        "/repos/bees/*",
        "/repos/bees/**",
        "/**",
        # Wildcards a hand-written config may hold anywhere: bees matches them too
        "/repos/bees*",
        "/repos/be*s",
        "/repos/*bees",
        "/repos/*/bees",
        "/*/bees",
        "/repos/**/",
        "/repos/**/bees",
        "**",
        "/repos**",
        "/repos/**/*",
        # Trailing slashes
        "/repos/bees/",
        "/repos/*/",
        "/repos/bees//",
    ],
)
def test_scope_rule_agrees_with_bees(pattern):
    """ci_bugs_hive.py runs without bees installed, so it copies bees' scope matching and ranking: they must agree."""
    segments, wildcard_tier = compute_scope_specificity(pattern)

    assert {root: cbh.scope_matches(pattern, root) for root in _SCOPE_ROOTS} == {
        root: match_scope_pattern(Path(root), pattern) for root in _SCOPE_ROOTS
    }
    assert cbh.compute_scope_specificity(pattern) == (segments, wildcard_tier)
    # bees ranks matching scopes by (segments, -wildcard tier): config.find_matching_scope
    assert cbh.scope_specificity(pattern) == (segments, -wildcard_tier)


def _run_bugs_hive_script(stdin, repo_root=ROOT):
    return subprocess.run(
        [sys.executable, str(BUGS_HIVE_SCRIPT), "--repo-root", str(repo_root)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "own_hives, other_scopes, queen, expected",
    [
        pytest.param(["bugs", "testplans"], {}, False, "bugs", id="bugs_hive"),
        pytest.param(["testplans"], {}, False, None, id="no_bugs_hive"),
        pytest.param(["bees_bugs"], {"{parent}/**": ["bugs"]}, False, "bees_bugs", id="own_scope_over_inherited"),
        pytest.param(["features"], {"{parent}/**": ["bugs"]}, False, "bugs", id="inherited_scope_if_own_has_none"),
        pytest.param(["bees_bugs"], {"{parent}/sibling": ["bugs"]}, True, "bees_bugs", id="queen_repo"),
    ],
)
def test_bugs_hive_script_reads_bees_list_hives(repo_with_hives, cli_runner, own_hives, other_scopes, queen, expected):
    """run_test.sh pipes `bees list-hives` run in the repo root into the script, and takes all of its stdout."""
    repo_root = repo_with_hives(*own_hives, other_scopes=other_scopes, queen=queen)
    list_hives_output, _ = cli_runner(["list-hives"])

    result = _run_bugs_hive_script(list_hives_output, repo_root.resolve())

    assert (result.returncode, result.stdout) == ((0, f"{expected}\n") if expected else (1, "")), result.stderr


@pytest.mark.parametrize(
    "stdin, relayed",
    [
        pytest.param("Error: bees: command not found", "", id="not_json"),
        pytest.param(json.dumps({"status": "error", "message": "config conflict"}), "config conflict", id="error"),
        pytest.param("[1, 2]", "", id="json_list"),
    ],
)
def test_bugs_hive_script_fails_on_input_that_is_not_a_hive_list(stdin, relayed):
    result = _run_bugs_hive_script(stdin)

    assert (result.returncode, result.stdout) == (1, ""), result.stderr
    assert relayed in result.stderr, "bees' own error message tells the user what to fix"


# ---------------------------------------------------------------------------
# file_bug
# ---------------------------------------------------------------------------


# No hive is named "bugs" (a built-in default would find it): discovery must pick team_bugs by the rule.
@pytest.mark.parametrize(
    "args, env, expected_hive",
    [
        pytest.param([], {"BEES_REPO_ROOT": "{repo}"}, "team_bugs", id="hive_discovered_from_server"),
        pytest.param(
            [], {"BEES_REPO_ROOT": "{repo}", "BEES_BUGS_HIVE": "triage"}, "triage", id="hive_env_over_discovery"
        ),
        pytest.param(
            ["--hive", "triage"],
            {"BEES_REPO_ROOT": "{repo}", "BEES_BUGS_HIVE": "features"},
            "triage",
            id="hive_option_over_env",
        ),
        pytest.param(
            ["--repo-root", "{repo}"],
            {"BEES_REPO_ROOT": "{repo}/elsewhere"},
            "team_bugs",
            id="repo_root_option_over_env",
        ),
    ],
)
def test_file_bug_files_into_the_hosts_bugs_hive(
    bees_server, repo_with_hives, monkeypatch, capsys, args, env, expected_hive
):
    """Regression b.g76: file_bug.py filed into one machine's hive name and repo root, whatever the host had."""
    repo_root = repo_with_hives("team_bugs", "triage", "features")

    code, out, err = _file_bug(monkeypatch, capsys, _with_repo(args, repo_root), _with_repo(env, repo_root))

    filed = re.fullmatch(r"BUG FILED: (\S+)\n", out)
    assert code == 0 and filed, err
    [ticket] = (repo_root / expected_hive).rglob(f"{filed[1]}.md")
    assert "CI Test 7: list hives" in ticket.read_text()


# No level offers "open", the status file_bug.py used to send, so each case would fail on it.
@pytest.mark.parametrize(
    "status_values, args, expected_status",
    [
        pytest.param({"team_bugs": ["draft", "defined", "active", "done"]}, [], "draft", id="apiary_bugs_hive"),
        pytest.param(
            {"team_bugs": ["draft", "done"], "scope": ["triaged", "fixed"], "global": ["new", "closed"]},
            [],
            "draft",
            id="hive_over_scope_and_global",
        ),
        pytest.param(
            {"team_bugs": [], "scope": ["triaged", "fixed"], "global": ["new", "closed"]},
            [],
            "triaged",
            id="empty_hive_list_falls_through_to_scope",
        ),
        pytest.param({"global": ["new", "closed"]}, [], "new", id="global_values"),
        pytest.param({"team_bugs": None, "scope": ["triaged"]}, [], "triaged", id="freeform_hive_takes_scope_value"),
        pytest.param({}, [], None, id="freeform_everywhere_no_status"),
        pytest.param({"team_bugs": ["draft", "done"]}, ["--hive", "Team-Bugs"], "draft", id="hive_name_not_normalized"),
    ],
)
def test_file_bug_gives_the_bug_the_hives_first_status(
    bees_server, repo_with_hives, monkeypatch, capsys, status_values, args, expected_status
):
    """Regression b.oax: file_bug.py sent status "open", which the Apiary Bugs hive (draft, defined, ...) refused."""
    repo_root = repo_with_hives("team_bugs", "triage", status_values=status_values)

    code, out, err = _file_bug(monkeypatch, capsys, args, {"BEES_REPO_ROOT": str(repo_root)})

    filed = re.fullmatch(r"BUG FILED: (\S+)\n", out)
    assert code == 0 and filed, err
    [ticket] = (repo_root / "team_bugs").rglob(f"{filed[1]}.md")
    assert parse_frontmatter(ticket)[0].get("status") == expected_status


def test_hive_name_normalization_agrees_with_bees():
    """file_bug.py runs without bees installed, so it copies bees' hive name normalization: they must agree."""
    names = ["team_bugs", "Team-Bugs", "My Bugs", "BUGS!", "9_bugs", "_bugs", "--", "", "Ünïcode-Bugs"]

    assert {name: fb.normalize_hive_name(name) for name in names} == {name: normalize_hive_name(name) for name in names}


@pytest.mark.parametrize(
    "hive_names, args, env, cause",
    [
        pytest.param(["team_bugs"], [], {}, "no repo root", id="no_repo_root"),
        pytest.param(
            ["triage", "features"], [], {"BEES_REPO_ROOT": "{repo}"}, "no bugs hive for", id="no_bugs_hive_found"
        ),
        pytest.param(
            ["team_bugs"],
            ["--hive", "no_such_hive"],
            {"BEES_REPO_ROOT": "{repo}"},
            "hive_not_found",
            id="server_rejects_ticket",
        ),
        pytest.param(
            ["team_bugs"],
            ["--hive", "team_bugs"],
            {"BEES_REPO_ROOT": "{repo}/elsewhere"},
            "get_status_values",
            id="status_values_unavailable",
        ),
        pytest.param(
            ["team_bugs"],
            ["--description", "x" * 10_001],
            {"BEES_REPO_ROOT": "{repo}"},
            "non-JSON",
            id="non_json_answer",
        ),
    ],
)
def test_file_bug_failure_prints_the_failure_line(
    bees_server, repo_with_hives, monkeypatch, capsys, hive_names, args, env, cause
):
    """Regression b.g76: a failed filing printed no line /ci polls for, so /ci waited forever."""
    repo_root = repo_with_hives(*hive_names)

    code, out, err = _file_bug(monkeypatch, capsys, _with_repo(args, repo_root), _with_repo(env, repo_root))

    assert (code, out) == (1, "")
    # The in-process server logs to stderr too; the failure line is file_bug.py's last word, and names the cause.
    failure = err.splitlines()[-1]
    assert failure.startswith("BUG FILING FAILED: ") and cause in failure, err
    assert not list(repo_root.rglob("b.*.md")), "nothing may be filed"


def test_file_bug_gives_up_on_a_server_that_stops_answering(hanging_mcp_server, monkeypatch, capsys, tmp_path):
    """Regression b.g76: a server that opened the session, then never answered, held the phase until /ci's deadline."""
    monkeypatch.setattr(fb, "FILE_BUG_TIMEOUT_SECONDS", 0.5)
    env = {"BUG_SERVER_URL": hanging_mcp_server.url, "BEES_REPO_ROOT": str(tmp_path), "BEES_BUGS_HIVE": "bugs"}

    start = time.monotonic()
    code, out, err = _file_bug(monkeypatch, capsys, [], env)
    elapsed = time.monotonic() - start

    assert "tools/call" in hanging_mcp_server.methods, "the session must be up before the server stops answering"
    assert (code, out) == (1, "")
    assert err.splitlines()[-1].startswith("BUG FILING FAILED: "), err
    # Given up at the limit: closing the session on the way out (a DELETE the server never answers) must not wait.
    assert elapsed < _HANG_SECONDS / 2


def test_file_bug_script_reports_an_unreachable_server(closed_port_url, tmp_path):
    """Regression b.g76: a connection error ended in a traceback, with no line /ci polls for."""
    env = {**os.environ, "BUG_SERVER_URL": closed_port_url, "BEES_REPO_ROOT": str(tmp_path), "BEES_BUGS_HIVE": "bugs"}

    result = subprocess.run(
        [sys.executable, str(FILE_BUG), "--title", "CI Test 7", "--description", "Got: 1"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr.startswith("BUG FILING FAILED: "), result.stderr
