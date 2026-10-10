"""
Tests for how a Claude-run CI phase ends: docker/ci_claude_stream.py, and docker/test_runner.sh running
Claude headless through it.

PURPOSE:
test_runner.sh runs a Claude phase as `claude -p ... --output-format stream-json`, piped into
ci_claude_stream.py. The script shows the run in the tmux pane /ci reads, and exits 0 only if Claude printed
a line /ci acts on: RELEASE TEST PHASE N PASSED, BUG FILED: or BUG FILING FAILED:. On any other exit,
test_runner.sh prints a TEST RUNNER EXITED line, so a run that gives up ends its phase at once (b.mqm: the
interactive session sat at its prompt until /ci's phase deadline). The script's tests feed it stream-json
events made up here. The test_runner.sh checks read the script as text and never run it.

SCOPE - Tests that belong here:
- the result lines it finds (in Claude's text anywhere, in a tool result only at the start of a line,
  never in a prompt), its exit code, and the result lines repeated as the last lines of the pane
- what the pane shows of a run: Claude's text, tool calls, tool results cut to their first lines, the MCP
  servers' status
- the outcome line (--outcome-file) of a run that finished, failed, or stopped with no final result
- events it cannot read, usage errors, and its exit code when nothing reads its output any more
- test_runner.sh runs Claude headless through it, from where the image installs it, with errexit off, and
  prints the crash line when it exits non-zero: one for no result line, another for a crash of the script

SCOPE - Tests that DON'T belong here:
- which runner runs each phase, and integration.sh's result lines -> test_integration_phases.py
- the Phase 4 HTTP server check, and the signals /ci polls for -> test_check_bees_server.py
"""

import io
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers import load_script

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "docker" / "ci_claude_stream.py"
TEST_RUNNER = REPO_ROOT / "docker" / "test_runner.sh"

ccs = load_script(SCRIPT)

# A command of test_runner.sh that runs Claude, exec'd or not
_CLAUDE_RUN = re.compile(r"\s*(?:exec\s+)?claude\s+(?!mcp\b)")
# set that turns errexit on (set -e, set -euo pipefail, set -o errexit) or off (set +e, set +o errexit)
_ERREXIT = re.compile(r"set [-+](?:[a-zA-Z]*e[a-zA-Z]*|o errexit)(?: .*)?")
# if [[ "${statuses[1]}" -eq 0 ]]; then: a test of the pipeline's 2nd status, the formatter's (operator, number)
_FORMATTER_STATUS_IF = re.compile(r'if \[\[? "?\$\{?\w+\[1\]\}?"? (-eq|-ne|==|!=) "?(\d+)"? \]\]?; then')
_OPERATORS = {"==": "-eq", "!=": "-ne"}


def _text(text):
    """An assistant message with one text block: what Claude says."""
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _tool_call(name, tool_input):
    block = {"type": "tool_use", "id": "toolu_1", "name": name, "input": tool_input}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def _tool_result(content, is_error=False):
    """A user message carrying a tool's output: a string, or a list of content blocks."""
    block = {"type": "tool_result", "tool_use_id": "toolu_1", "content": content, "is_error": is_error}
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def _prompt(text):
    """A user message with text: a prompt, such as the expanded skill."""
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _end(text, is_error=False, subtype="success"):
    """The result event that closes a run."""
    return {"type": "result", "subtype": subtype, "is_error": is_error, "result": text, "num_turns": 9}


@pytest.fixture
def run_stream(monkeypatch, capsys, tmp_path):
    """Runs ci_claude_stream.main on events (dicts, or raw lines) as stdin: exit code, pane lines, outcome."""
    outcome_file = tmp_path / "outcome.txt"

    def run(*events):
        raw = "".join(f"{event if isinstance(event, str) else json.dumps(event)}\n" for event in events)
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw.encode())))
        code = ccs.main(["--phase", "4", "--outcome-file", str(outcome_file)])
        return SimpleNamespace(code=code, pane=capsys.readouterr().out.splitlines(), outcome=outcome_file.read_text())

    return run


# ---------------------------------------------------------------------------
# Result lines and exit code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "events, results",
    [
        pytest.param(
            [_text("12 of 12 tests passed.\n\nRELEASE TEST PHASE 4 PASSED"), _end("RELEASE TEST PHASE 4 PASSED")],
            ["RELEASE TEST PHASE 4 PASSED"],
            id="passed_in_claudes_text",
        ),
        pytest.param([_text("**RELEASE TEST PHASE 4 PASSED**")], ["**RELEASE TEST PHASE 4 PASSED**"], id="markdown"),
        pytest.param(
            [_tool_call("Bash", {"command": "python file_bug.py --title t"}), _tool_result("ok\nBUG FILED: b.x7k")],
            ["BUG FILED: b.x7k"],
            id="bug_filed_by_file_bug_py",
        ),
        pytest.param(
            [_tool_result([{"type": "text", "text": "BUG FILING FAILED: no bugs hive"}], is_error=True)],
            ["BUG FILING FAILED: no bugs hive"],
            id="bug_filing_failed_in_a_failed_tool_call",
        ),
        pytest.param(
            [_text("RELEASE TEST PHASE 3 PASSED"), _text("RELEASE TEST PHASE 41 PASSED")], [], id="another_phase_passed"
        ),
        # A file Claude read: quoting a result line is not printing one
        pytest.param([_tool_result('        print(f"BUG FILED: {ticket_id}")')], [], id="tool_result_quotes_one"),
        # The skill text quotes every result line
        pytest.param([_prompt("When all tests pass, print:\nRELEASE TEST PHASE 4 PASSED")], [], id="prompt_quotes_one"),
        pytest.param([_text("bees-http has no tools. Stopping."), _end("Stopping.")], [], id="claude_gave_up"),
    ],
)
def test_exits_0_only_for_a_result_line_and_repeats_it_last(run_stream, events, results):
    """Regression b.mqm: a Claude run that gave up without a result line held its phase until /ci's deadline."""
    run = run_stream(*events)
    header = run.pane.index(ccs.RESULT_HEADER) if ccs.RESULT_HEADER in run.pane else len(run.pane)

    assert run.code == (0 if results else 1)
    # The last lines of the pane, which /ci captures; each line once, though Claude's final text repeats it
    assert run.pane[header + 1 :] == results


# ---------------------------------------------------------------------------
# What the pane shows
# ---------------------------------------------------------------------------


def test_pane_shows_the_run_but_no_prompt(run_stream):
    """A person reads the pane when a phase fails. The skill text is no part of the run, and it quotes result lines."""
    long_line = "x" * (ccs.MAX_LINE_CHARS + 50)
    output = [long_line, *(f"line {n}" for n in range(2, 13)), "BUG FILED: b.x7k"]
    servers = [{"name": "bees-http", "status": "failed"}]
    init = {"type": "system", "subtype": "init", "model": "m", "mcp_servers": servers}

    run = run_stream(
        init,
        _prompt("SKILL TEXT: you are a strict test runner"),
        _text("Running Test 1."),
        _tool_call("Bash", {"command": "bees list-hives\n  --verbose"}),
        _tool_result("\n".join(output)),
    )
    pane = "\n".join(run.pane)
    shown = [n for n in range(2, 13) if f"line {n}\n" in f"{pane}\n"]

    assert "bees-http (failed)" in pane
    assert "SKILL TEXT" not in pane
    assert "Running Test 1." in run.pane
    assert any("Bash" in line and "bees list-hives --verbose" in line for line in run.pane), "one line per call"
    # A tool result's first lines, each cut to a length; a result line past them is shown too
    assert shown == list(range(2, ccs.TOOL_RESULT_LINES + 1))
    assert long_line not in pane and long_line[: ccs.MAX_LINE_CHARS] in pane
    assert any(line.endswith("BUG FILED: b.x7k") for line in run.pane[: run.pane.index(ccs.RESULT_HEADER)])


# ---------------------------------------------------------------------------
# Outcome of a run without a result line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "events, says, shown",
    [
        pytest.param(
            [_text("Stopping: bees-http\nhas no tools."), _end("Stopping: bees-http\nhas no tools.")],
            ["finished", "Stopping: bees-http has no tools."],
            "Stopping: bees-http",
            id="finished_without_a_result_line",
        ),
        pytest.param(
            [_end("API Error: 401 invalid token", is_error=True, subtype="error_during_execution")],
            ["failed", "API Error: 401 invalid token"],
            "API Error: 401 invalid token",
            id="run_failed",
        ),
        pytest.param(
            [_text("Running Test 1."), "Segmentation fault"], ["no final result"], "Segmentation fault", id="cut_short"
        ),
    ],
)
def test_outcome_says_in_one_line_how_the_run_ended(run_stream, events, says, shown):
    """test_runner.sh puts the outcome on its TEST RUNNER EXITED line: the reason /ci gives for the crash."""
    run = run_stream(*events)

    assert run.code == 1
    assert run.outcome.count("\n") == 1 and run.outcome.endswith("\n")
    assert [part for part in says if part not in run.outcome] == []
    # The error itself is in the pane, also when Claude never said it
    assert shown in "\n".join(run.pane)


def test_events_it_cannot_read_do_not_stop_it(run_stream):
    """It must read to the end: if it stopped, Claude would lose its output pipe, and its run would end."""
    run = run_stream(
        "not json",
        "[1, 2]",
        {"type": "assistant", "message": None},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": None}, "stray"]}},
        {"type": "system", "subtype": "init", "mcp_servers": 5},
        {"type": "stream_event"},
        {"type": "assistant", "message": {"content": "RELEASE TEST PHASE 4 PASSED"}},
    )

    assert run.code == 0
    assert "not json" in run.pane
    assert run.pane[-2:] == [ccs.RESULT_HEADER, "RELEASE TEST PHASE 4 PASSED"]


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no_phase"),
        pytest.param(["--phase", "0"], id="phase_zero"),
        pytest.param(["--phase", "4a"], id="not_a_phase_number"),
    ],
)
def test_usage_errors_exit_2(argv):
    with pytest.raises(SystemExit) as exc_info:
        ccs.main(argv)

    assert exc_info.value.code == 2


@pytest.mark.parametrize("pane_gone", [pytest.param(False, id="pane"), pytest.param(True, id="pane_gone")])
@pytest.mark.parametrize(
    "events, expected_code",
    [
        pytest.param([_text("RELEASE TEST PHASE 4 PASSED")], 0, id="result_line"),
        pytest.param([_text("Stopping."), _end("Stopping.")], 1, id="no_result_line"),
    ],
)
def test_script_from_command_line(tmp_path, events, expected_code, pane_gone):
    """As test_runner.sh runs it: the stream on stdin (bytes that are not UTF-8 too), its exit status read after.
    With nothing reading its output, it exited 120 whatever it saw: Python failed to flush that output at exit, and
    test_runner.sh took that status for a crash of the script."""
    stdin = b"\xff\xfe not UTF-8\n" + "".join(json.dumps(event) + "\n" for event in events).encode()
    outcome = tmp_path / "outcome.txt"

    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--phase", "4", "--outcome-file", str(outcome)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if pane_gone:
        process.stdout.close()
    _, stderr = process.communicate(stdin, timeout=30)

    assert process.returncode == expected_code, stderr
    assert outcome.read_text().strip()


# ---------------------------------------------------------------------------
# test_runner.sh (static: read as text, never run)
# ---------------------------------------------------------------------------


def _test_runner_commands():
    """test_runner.sh, one command per line: backslash-continued lines joined, comment lines dropped."""
    lines = TEST_RUNNER.read_text().replace("\\\n", " ").splitlines()
    return [line for line in lines if not line.lstrip().startswith("#")]


def _claude_runs(commands):
    """(index, command) of each command that runs Claude: `claude mcp` only registers a server."""
    return [(i, command) for i, command in enumerate(commands) if _CLAUDE_RUN.match(command)]


def test_test_runner_runs_claude_headless_through_the_formatter():
    """Regression b.mqm: `exec claude "/release-test"` ran an interactive session, which sits at its prompt once the
    run is over, so a run that gave up without a result line held its phase until /ci's deadline."""
    runs = _claude_runs(_test_runner_commands())
    dockerfile = (REPO_ROOT / "docker" / "Dockerfile.test").read_text()

    assert len(runs) == 1, [command for _, command in runs]
    [(_, command)] = runs
    claude, _, formatter = command.partition(" | ")
    installed = re.fullmatch(r'\s*python3 (\S+/ci_claude_stream\.py) --phase "\$\{?PHASE\}?"(?: .*)?', formatter)
    # -p exits when the run is over; stream-json (which -p allows only with --verbose) is what the formatter reads
    assert re.search(r"\s(?:-p|--print)\s", claude), command
    assert "--output-format stream-json" in claude and "--verbose" in claude, command
    # Nothing can answer a prompt in the container, and a strict test runner takes a denied tool call for a bug
    assert "< /dev/null" in claude and "--dangerously-skip-permissions" in claude, command
    assert installed, f"Claude's output must go through ci_claude_stream.py: {command}"
    assert re.search(rf"^COPY docker/ci_claude_stream\.py {re.escape(installed[1])}$", dockerfile, re.M)


def test_test_runner_reads_the_claude_runs_statuses_with_errexit_off():
    """Under set -e, a run without a result line (the formatter's status 1) would end test_runner.sh before its crash
    line, with only entrypoint.sh's TEST RUNNER EXITED (status 1): no reason."""
    commands = _test_runner_commands()
    [(run, _)] = _claude_runs(commands)
    # From the start of the function that runs Claude, if one does
    start = max((i for i in range(run) if re.fullmatch(r"\w+\(\) \{", commands[i])), default=0)
    errexit = [command.strip() for command in commands[start:run] if _ERREXIT.fullmatch(command.strip())]

    assert errexit and errexit[-1].startswith("set +"), errexit
    # Any command run between them resets PIPESTATUS
    assert "PIPESTATUS" in commands[run + 1]


def test_test_runner_tells_a_run_without_a_result_line_from_a_formatter_crash():
    """Regression b.mqm: /ci handles TEST RUNNER EXITED without a result line above it as a crash, at once. The
    formatter's status decides (under pipefail, the pipeline's status is Claude's whenever Claude's is not 0): 0 is a
    result line seen, 1 none, any other a crash of ci_claude_stream.py, which says nothing about Claude's run."""
    commands = _test_runner_commands()
    [(run, _)] = _claude_runs(commands)
    after = [command.strip() for command in commands[run + 1 : commands.index("}", run)]]
    branches = {}
    for i, command in enumerate(after):
        if m := _FORMATTER_STATUS_IF.fullmatch(command):
            end = after.index("fi", i)
            branches[(_OPERATORS.get(m[1], m[1]), int(m[2]))] = SimpleNamespace(at=i, end=end, body=after[i + 1 : end])
    passed, crashed = branches.get(("-eq", 0)), branches.get(("-ne", 1))

    assert passed and passed.body == ["return 0"], branches
    # Before the crash branch, which 0 would otherwise enter
    assert crashed and passed.at < crashed.at, branches
    assert crashed.body[0].startswith('echo "TEST RUNNER EXITED: ') and "[1]" in crashed.body[0], crashed.body
    assert re.fullmatch(r"return [1-9]\d*", crashed.body[-1]), crashed.body
    # Status 1: the crash line with how the run ended
    rest = after[crashed.end + 1 :]
    no_result = next((i for i, command in enumerate(rest) if command.startswith('echo "TEST RUNNER EXITED: ')), None)
    assert no_result is not None and re.fullmatch(r"return [1-9]\d*", rest[-1]), rest
