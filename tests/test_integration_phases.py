"""
Static checks that tests/integration.sh runs only the phase in $PHASE, and that docker/test_runner.sh
gives every phase of test plan b.qi9 one runner.

PURPOSE:
CI runs each phase of b.qi9 in its own container. docker/test_runner.sh runs some phases with
tests/integration.sh and the others with Claude (/release-test). integration.sh tags each test section
with its phase (phase_section), runs only the tests of the phase in $PHASE, and prints
`RELEASE TEST PHASE <N> PASSED`, the line /ci waits for. These tests read both scripts as text and never
run them: integration.sh overwrites the global bees config. Only `bash -n` (parse, run nothing) touches them.

SCOPE - Tests that belong here:
- integration.sh: every test section is tagged with one of its phases, the phase is checked before any
  test runs, run_test skips the tests of other phases, and the pass and fail lines name the phase
- the sections each phase runs
- test_runner.sh: requires a phase number, passes it on, and runs integration.sh's phases with it
- every phase of the plan runs under one runner, and the MCP server phases under Claude

SCOPE - Tests that DON'T belong here:
- the result lines /ci polls for, ports and portability of the CI files -> test_check_bees_server.py
- how /ci reads the plan (ci_plan.py) -> test_ci_skill.py
"""

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers import load_script

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = REPO_ROOT / "tests" / "integration.sh"
TEST_RUNNER = REPO_ROOT / "docker" / "test_runner.sh"

cp = load_script(REPO_ROOT / "docker" / "ci_plan.py")

# "# === PHASE 2: TICKET CRUD ===" heads a section of Phase 2, "# === HELPER FUNCTIONS ===" one of no phase
_HEADER = re.compile(r"# === (?:PHASE (\d+): )?(.+?) ===")
# An `if` over the phase in test_runner.sh: if [[ "$PHASE" == "1" || "$PHASE" == "2" ]]; then
_PHASE_IF = re.compile(r'if \[\[ "\$PHASE" == "\d+"(?: \|\| "\$PHASE" == "\d+")* \]\]; then')
# test_runner.sh's check of the phase number: if [[ ! "$PHASE" =~ <pattern> ]]; then
_PHASE_CHECK = re.compile(r'if \[\[ ! "\$PHASE" =~ (\S+) \]\]; then')
# $PHASE or ${PHASE}, not $SECTION_PHASE
_PHASE_REF = re.compile(r"\$\{?PHASE\b")
_EXIT_ERROR = re.compile(r"\s*exit [1-9]\d*")
# A built-in phase (${PHASE:-1}); ${PHASE:-} only keeps `set -u` from failing
_DEFAULT_PHASE = re.compile(r"\$\{PHASE:-[^}]")
# "$A" != "$B", quotes and ${} braces optional: the names of the two variables
_VAR = r'"?\$\{?(\w+)\}?"?'
_NOT_EQUAL = re.compile(rf"{_VAR}\s+!=\s+{_VAR}")

# The sections each phase runs, as the b.qi9 epics describe the phases. Asserted by name, not by test count:
# a count changes with every test added, while a section moves to another phase only by a decision about the plan.
PHASE_SECTIONS = {
    1: {"INSTALLATION"},
    2: {
        "HIVE MANAGEMENT",
        "TIER CONFIGURATION",
        "TICKET CRUD",
        "DEPENDENCIES",
        "ID AND GUID VALIDATION",
        "STATUS BEHAVIOR",
        "FREEFORM QUERIES",
        "NAMED QUERIES",
        "BODY FILE / CHUNK FILE",
    },
    5: {
        "INDEX GENERATION",
        "UNDERTAKER",
        "MOVE BEE",
        "SANITIZER",
        "ERROR HANDLING",
        "TEST CONFIG MODE",
        "SETUP COMMAND",
        "STING COMMAND",
        "STATUS VALUES",
        "GLOB-SCOPE STATUS VALUES (bug b.7qj)",
        "UNINSTALL SEQUENCE",
        "CLONE BEE",
        "FAST PARSER PIPELINE",
        "COLONIZE --SCOPE",
        "SCOPE-AWARE HIVE REGISTRATION",
        "CROSS-SCOPE INHERITANCE",
        "ID CHARSET AND HIERARCHICAL IDS",
        "SINGLE TESTS",
        "HIVE PORTABILITY: IDENTITY.JSON (b.f6y)",
    },
    6: {"REFERENCE MATERIALS", "UPDATE CONFIG", "RESOLVER REGISTRY"},
}
# Setup and the end of the script: no tests
UNTAGGED_SECTIONS = {"CONFIGURATION", "HELPER FUNCTIONS", "PHASE SELECTION", "SUCCESS SIGNAL"}


def _numbered_lines():
    return list(enumerate(INTEGRATION.read_text().splitlines(), start=1))


def _sections():
    """integration.sh's sections: header phase (None if none), name, and the (number, line) pairs to the next header."""
    sections = []
    for number, line in _numbered_lines():
        if header := _HEADER.fullmatch(line):
            phase = int(header[1]) if header[1] else None
            sections.append(SimpleNamespace(phase=phase, name=header[2], line=number, lines=[]))
        elif sections:
            sections[-1].lines.append((number, line))
    return sections


def _section_lines(name):
    return [line for section in _sections() if section.name == name for _, line in section.lines]


def _calls(numbered_lines, command):
    """(line number, argument) of each ``command <argument>`` call among (number, line) pairs."""
    return [(number, m[1]) for number, line in numbered_lines if (m := re.fullmatch(rf"\s*{command}\s+(\S+)", line))]


def _function_body(name):
    lines = INTEGRATION.read_text().splitlines()
    start = lines.index(f"{name}() {{")
    return lines[start + 1 : lines.index("}", start)]


def _script_phases():
    """SCRIPT_PHASES: the phases integration.sh runs."""
    found = re.findall(r"^SCRIPT_PHASES=\(([\d ]*)\)$", INTEGRATION.read_text(), re.M)
    assert len(found) == 1, f"integration.sh must list its phases in one SCRIPT_PHASES=(...) line, found {len(found)}"
    return {int(phase) for phase in found[0].split()}


def _test_runner_phase_blocks():
    """(phases, text) of each `if` over $PHASE in test_runner.sh."""
    lines = TEST_RUNNER.read_text().splitlines()
    return [
        ({int(p) for p in re.findall(r'"\$PHASE" == "(\d+)"', line)}, "\n".join(lines[i + 1 : lines.index("fi", i)]))
        for i, line in enumerate(lines)
        if _PHASE_IF.fullmatch(line)
    ]


def _phases_test_runner_runs_with_the_script():
    """The phases test_runner.sh hands to integration.sh with exec: they never reach the Claude launch below it."""
    routed = [
        phases
        for phases, text in _test_runner_phase_blocks()
        if re.search(r"^\s*exec bash \S*tests/integration\.sh\b", text, re.M)
    ]
    assert len(routed) == 1, "test_runner.sh must exec integration.sh in one `if` over $PHASE"
    return routed[0]


# ---------------------------------------------------------------------------
# Routing: which runner runs each phase
# ---------------------------------------------------------------------------


def test_test_runner_runs_the_scripts_phases_with_it():
    """A phase on one list only either runs none of the script's sections (Claude runs it) or stops at the check."""
    assert _phases_test_runner_runs_with_the_script() == _script_phases()


def test_plan_phases_each_run_under_one_runner():
    """Every phase the script runs is one /ci launches, and the phases test_runner.sh starts an MCP server for
    run under Claude. Every other phase falls through to the Claude launch, so none is left without a runner."""
    plan = {phase["phase"] for phase in cp.read_plan(cp.TESTPLANS_PATH)}
    script = _script_phases()
    servers = set().union(*(phases for phases, text in _test_runner_phase_blocks() if "claude mcp add" in text))

    assert script <= plan, f"phases of the script that the plan does not have: {sorted(script - plan)}"
    assert servers, "found no phase test_runner.sh starts an MCP server for"
    assert servers <= plan - script, f"MCP server phases run by integration.sh: {sorted(servers & script)}"


def test_test_runner_requires_a_phase_number_and_exports_it():
    """It ran a container without PHASE as Phase 1. integration.sh and Claude both read PHASE from the environment."""
    text = TEST_RUNNER.read_text()
    lines = text.splitlines()
    checks = [(i, m[1]) for i, line in enumerate(lines) if (m := _PHASE_CHECK.fullmatch(line))]
    exports = [i for i, line in enumerate(lines) if re.fullmatch(r"export PHASE\b.*", line)]
    first_route = min(i for i, line in enumerate(lines) if _PHASE_IF.fullmatch(line))

    assert not _DEFAULT_PHASE.search(text)
    assert len(checks) == 1, "test_runner.sh must check PHASE against a pattern"
    [(check, pattern)] = checks
    # Routing compares strings: "01" would reach Claude, not integration.sh
    candidates = ["", "x", "0", "01", "-1", "1 2", "1", "6", "12"]
    assert [phase for phase in candidates if re.fullmatch(pattern, phase)] == ["1", "6", "12"]
    assert any(_EXIT_ERROR.fullmatch(line) for line in lines[check : lines.index("fi", check)])
    assert exports and check < exports[0] < first_route


# ---------------------------------------------------------------------------
# integration.sh: phase selection and sections
# ---------------------------------------------------------------------------


def test_phase_is_checked_before_any_test_runs():
    """Regression b.aqj: the script ignored $PHASE, so every phase ran every test."""
    lines = _numbered_lines()
    selection = next((section for section in _sections() if section.name == "PHASE SELECTION"), None)
    first_test = min(number for number, _ in _calls(lines, "run_test"))
    first_section = min((number for number, _ in _calls(lines, "phase_section")), default=first_test)

    assert selection, "integration.sh must select the phase in a PHASE SELECTION section"
    checks = [line for _, line in selection.lines if line.startswith("if ") and _PHASE_REF.search(line)]
    exits = [number for number, line in selection.lines if _EXIT_ERROR.fullmatch(line)]
    assert checks and exits, "PHASE SELECTION must stop the script when $PHASE is not one of its phases"
    assert max(exits) < first_test
    assert first_section < first_test, "a test before the first phase_section belongs to no phase"
    assert not _DEFAULT_PHASE.search(INTEGRATION.read_text())


def test_run_test_runs_only_the_tests_of_the_phase_in_PHASE():
    """Regression b.aqj: run_test skipped only the tests below START_TEST, whatever their phase."""
    body = [line.strip() for line in _function_body("run_test")]
    call = body.index('"$fn"')
    # [ "$SECTION_PHASE" != "$PHASE" ] || [ "$TEST_NUM" -lt "$START_TEST" ], or one [[ ... || ... ]]
    skips = [
        (i, [operand.strip(" []") for operand in m[1].split("||")])
        for i, line in enumerate(body[:call])
        if (m := re.fullmatch(r"if (.+); then", line)) and "SECTION_PHASE" in line
    ]

    assert len(skips) == 1, "run_test must check the section's phase in one `if` before it runs the test"
    [(skip, operands)] = skips
    # Either check alone skips the test: with `&&`, every phase ran every test from START_TEST on
    compared = [{m[1], m[2]} for operand in operands if (m := _NOT_EQUAL.fullmatch(operand))]
    assert compared == [{"SECTION_PHASE", "PHASE"}], f"run_test must skip when $SECTION_PHASE != $PHASE: {operands}"
    assert any("START_TEST" in operand for operand in operands), f"no START_TEST check joined by ||: {operands}"
    assert re.fullmatch(r"return(?: 0)?", body[skip + 1]), "the skip must return before the test runs"
    # RUN_COUNT counts only the tests that ran: the pass line's count, and no pass without one
    assert any(line.startswith("RUN_COUNT=") for line in body[skip + 2 : call])
    assert 'SECTION_PHASE="$1"' in [line.strip() for line in _function_body("phase_section")]


def test_every_phase_header_is_followed_by_its_phase_section():
    """A test belongs to the phase of the last phase_section: each phase header sets it on the next line."""
    sections = _sections()
    tagged = [section for section in sections if section.phase is not None]
    starts = {section.line + 1 for section in tagged}
    calls = _calls(_numbered_lines(), "phase_section")

    assert tagged
    mismatched = [s.name for s in tagged if not s.lines or s.lines[0][1] != f"phase_section {s.phase}"]
    assert mismatched == [], "phase headers not followed by phase_section of the same phase"
    assert sorted({section.phase for section in tagged} - _script_phases()) == [], "phases not in SCRIPT_PHASES"
    assert [number for number, _ in calls if number not in starts] == [], "phase_section calls not after a header"


def test_only_setup_and_end_headers_have_no_phase():
    """Regression b.aqj: headers such as `PHASE 2 GROUP A:` and `FORMER PHASE 5 GROUP B:` set no phase."""
    untagged = [section for section in _sections() if section.phase is None]

    assert {section.name for section in untagged} == UNTAGGED_SECTIONS
    assert [section.name for section in untagged if _calls(section.lines, "run_test")] == []


def test_each_phase_runs_its_sections_of_the_plan():
    """Regression b.aqj: no section had a phase, so Phases 1, 2 and 5 each ran every section, Phase 6's too."""
    runs = {}
    for section in _sections():
        if section.phase is not None and _calls(section.lines, "run_test"):
            runs.setdefault(section.phase, set()).add(section.name)

    assert runs == PHASE_SECTIONS


# ---------------------------------------------------------------------------
# integration.sh: result lines
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block, result, exits_after",
    [
        pytest.param("fail_test", "FAILED", True, id="fail_line_then_exit"),
        pytest.param("SUCCESS SIGNAL", "PASSED", False, id="pass_line_at_the_end"),
    ],
)
def test_result_line_names_the_phase_that_ran(block, result, exits_after):
    """Regression b.aqj: every run printed RELEASE TEST PHASE 2 PASSED, so /ci never saw Phases 1 and 5 pass."""
    lines = _function_body(block) if block == "fail_test" else _section_lines(block)
    result_line = re.compile(rf"\becho\b.*RELEASE TEST PHASE (\S+) {result}\b")
    printed = [(i, m[1]) for i, line in enumerate(lines) if (m := result_line.search(line))]

    assert [phase for _, phase in printed] in (["$PHASE"], ["${PHASE}"]), printed
    assert any(_EXIT_ERROR.fullmatch(line) for line in lines[printed[0][0] :]) == exits_after
    assert not re.search(r"RELEASE TEST PHASE \d", INTEGRATION.read_text())


def test_a_phase_passes_only_if_one_of_its_tests_ran():
    """With START_TEST past a phase's last test, no test ran, and the phase would still pass."""
    lines = _section_lines("SUCCESS SIGNAL")
    passed = next(i for i, line in enumerate(lines) if "RELEASE TEST PHASE" in line)
    guard = next((i for i, line in enumerate(lines) if line.startswith("if ") and "RUN_COUNT" in line), passed)

    assert guard < passed, "SUCCESS SIGNAL must check RUN_COUNT before the pass line"
    assert any(_EXIT_ERROR.fullmatch(line) for line in lines[guard:passed])


@pytest.mark.parametrize("script", [INTEGRATION, TEST_RUNNER], ids=lambda path: path.name)
def test_script_parses(script):
    """`bash -n` parses without running anything."""
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stderr
