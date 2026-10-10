"""
Static checks that tests/integration.sh runs only the phase in $PHASE, and that docker/test_runner.sh
gives every phase of test plan b.qi9 one runner.

PURPOSE:
CI runs each phase of b.qi9 in its own container. docker/test_runner.sh runs some phases with
tests/integration.sh and the others with Claude (/release-test). integration.sh tags each test section
with its phase (phase_section), runs only the tests of the phase in $PHASE, and prints
`RELEASE TEST PHASE <N> PASSED`, the line /ci waits for. These tests read both scripts as text and never
run them: integration.sh overwrites the global bees config. Only `bash -n` (parse, run nothing) touches them
whole. The start test number tests run a copy of integration.sh's helper functions and of its phase_section
and test calls with bash, each test a stub that runs no command.

SCOPE - Tests that belong here:
- integration.sh: every test section is tagged with one of its phases, the phase is checked before any
  test runs, run_test skips the tests of other phases, and the pass and fail lines name the phase
- integration.sh: a start test number still runs the setup tests the tests from it on need, and no other
  test below it
- integration.sh: an error outside the assert helpers fails the running test through fail_test (ERR and
  EXIT traps), and fail_test ends in a bug filing line even when file_bug.py prints none
- the sections each phase runs
- test numbers: every test of integration.sh and every test titled `Test <N>:` in b.qi9 belongs to one phase, the one
  whose `Tests in this phase:` range holds it, only Claude phases' tests carry `Test <N>:` titles, and `/ci <N>` finds
  that phase as the /ci skill describes
- the Claude phases' tests as /release-test collects them: every Test Area has test cases, and every test case has a
  `Test <N>:` title in its phase's range, numbered above its up_dependencies, test cases of its own Test Area
- test_runner.sh: requires a phase number, passes it on, and runs integration.sh's phases with it
- test_runner.sh: a failing setup command ends it with a crash line naming the command (ERR trap), and the trap
  is cleared before integration.sh or Claude starts
- every phase of the plan runs under one runner, and the MCP server phases under Claude

SCOPE - Tests that DON'T belong here:
- the result lines /ci polls for, ports and portability of the CI files -> test_check_bees_server.py
- how /ci reads the plan (ci_plan.py) -> test_ci_skill.py
- how test_runner.sh runs Claude and ends a Claude phase (ci_claude_stream.py) -> test_ci_claude_stream.py
"""

import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers import load_script

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = REPO_ROOT / "tests" / "integration.sh"
TEST_RUNNER = REPO_ROOT / "docker" / "test_runner.sh"

cp = load_script(REPO_ROOT / "docker" / "ci_plan.py")
TESTPLANS = cp.TESTPLANS_PATH

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
# trap '<handler> <args>' <signal>, or trap <handler> <signal>; `trap - <signal>` (removing one) does not match
_TRAP = re.compile(r"trap '?(?P<handler>\w+)(?P<args>[^']*)'? (?P<signal>[A-Z]+)")
# set -E, alone or with other options (set -eE, set -Eeuo pipefail), or set -o errtrace
_ERRTRACE = re.compile(r"set -[a-zA-Z]*E[a-zA-Z]*(?: \w+)?|set -o errtrace")
# An epic's range, as /ci reads it: "Tests in this phase: 84-178", or with an en dash
_PHASE_RANGE = re.compile(r"Tests in this phase: (\d+)[-–](\d+)")
# A test titled "Test <N>:", as /ci finds it: grep -rlE "^title: '?Test <N>:" docker/testplans/b.qi9
_TITLED_TEST = re.compile(r"^title: '?Test (\d+):", re.M)
# integration.sh's calls that run a test, and how long each holds a test numbered below START_TEST for the tests after
# it (bug b.m4k): run_test not at all, a setup test to the end of its section or of its phase
_HOLDS = {"run_test": None, "run_setup_test": "section", "run_phase_setup_test": "phase"}
_RUN = f"(?:{'|'.join(_HOLDS)})"
# pass_test's line: [PASS] Test 179: test_ref_setup
_PASSED = re.compile(r"^\[PASS\] Test (\d+): (\w+)$", re.M)

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


def _function_body(name, script=INTEGRATION):
    lines = script.read_text().splitlines()
    start = lines.index(f"{name}() {{")
    return lines[start + 1 : lines.index("}", start)]


def _script_phases():
    """SCRIPT_PHASES: the phases integration.sh runs."""
    found = re.findall(r"^SCRIPT_PHASES=\(([\d ]*)\)$", INTEGRATION.read_text(), re.M)
    assert len(found) == 1, f"integration.sh must list its phases in one SCRIPT_PHASES=(...) line, found {len(found)}"
    return {int(phase) for phase in found[0].split()}


def _first_test_index(lines):
    return min(i for i, line in enumerate(lines) if re.match(rf"{_RUN}\s", line))


def _script_tests():
    """integration.sh's tests in order: number (run_test numbers every test, whatever its phase), function, the phase
    and section (index) of the phase_section above it, and how long it is held below START_TEST (_HOLDS)."""
    tests, phase, section = [], None, -1
    for line in INTEGRATION.read_text().splitlines():
        if m := re.fullmatch(r"phase_section (\d+)", line):
            phase, section = int(m[1]), section + 1
        elif m := re.fullmatch(rf"\s*({_RUN})\s+(\S+)", line):
            test = SimpleNamespace(number=len(tests) + 1, fn=m[2], phase=phase, section=section, hold=_HOLDS[m[1]])
            tests.append(test)
    return tests


def _script_test_numbers():
    """{phase: test numbers} of integration.sh."""
    numbers = {}
    for test in _script_tests():
        numbers.setdefault(test.phase, []).append(test.number)
    return numbers


def _replay_script():
    """integration.sh's test selection, to run with bash: its CONFIGURATION variables, its helper functions, its
    phase_section and test calls in order, and its SUCCESS SIGNAL. Each test is a stub that only passes: no bees
    command, no environment guard, no trap."""
    config = [line for line in _section_lines("CONFIGURATION") if re.match(r"[A-Z_]+=", line)]
    helpers, inside = [], False
    for line in _section_lines("HELPER FUNCTIONS"):
        inside = inside or bool(re.fullmatch(r"\w+\(\) \{", line))
        if inside or re.fullmatch(r"\w+\(\) \{.*\}", line):
            helpers.append(line)
        inside = inside and line != "}"
    stubs = [f"{test.fn}() {{ pass_test {test.fn}; }}" for test in _script_tests()]
    calls = [
        line
        for section in _sections()
        if section.phase is not None
        for _, line in section.lines
        if re.fullmatch(rf"phase_section \d+|\s*{_RUN}\s+\S+", line)
    ]
    return "\n".join(["set -euo pipefail", *config, *helpers, *stubs, *calls, *_section_lines("SUCCESS SIGNAL")])


def _plan_numbers():
    """The plan's test numbers, from the files /ci reads: {epic ID: phase}, {phase: range} from each epic's `Tests in
    this phase:` line, and (number, epic) of each test titled `Test <N>:`, its epic the directory right below b.qi9."""
    plan_dir = TESTPLANS / cp.PLAN_ID
    epics = {phase["id"]: phase["phase"] for phase in cp.read_plan(TESTPLANS)}
    ranges = {}
    for epic, phase in epics.items():
        found = _PHASE_RANGE.findall((plan_dir / epic / f"{epic}.md").read_text(encoding="utf-8"))
        assert len(found) == 1, f"epic {epic} (Phase {phase}) must give one `Tests in this phase:` range: {found}"
        ranges[phase] = range(int(found[0][0]), int(found[0][1]) + 1)
    titled = [
        (int(number), path.relative_to(plan_dir).parts[0])
        for path in sorted(plan_dir.rglob("*.md"))
        for number in _TITLED_TEST.findall(path.read_text(encoding="utf-8"))
    ]
    return SimpleNamespace(epics=epics, ranges=ranges, titled=titled)


def _claude_test_areas():
    """The Claude phases' tests as /release-test collects them, from the plan's files: {phase: {Test Area ID: [test
    case]}}, the Test Areas the epic's `children`, the test cases each Test Area's. A test case: its ID, the number of
    its `Test <N>:` title as /ci finds it (None without one), and its up_dependencies."""
    plan_dir = TESTPLANS / cp.PLAN_ID

    def ticket(*ids):
        path = plan_dir.joinpath(*ids, f"{ids[-1]}.md")
        fields, title = cp.read_frontmatter(path), _TITLED_TEST.search(path.read_text(encoding="utf-8"))
        up = fields.get("up_dependencies") or []
        return SimpleNamespace(id=ids[-1], children=fields.get("children") or [], number=title and int(title[1]), up=up)

    script_phases = _script_phases()
    return {
        phase["phase"]: {
            area: [ticket(phase["id"], area, case) for case in ticket(phase["id"], area).children]
            for area in ticket(phase["id"]).children
        }
        for phase in cp.read_plan(TESTPLANS)
        if phase["phase"] not in script_phases
    }


def _spans(numbers):
    """Sorted numbers as their runs, for readable failures: [1, 2, 3, 7] -> "1-3, 7"."""
    runs = []
    for number in sorted(numbers):
        if runs and number == runs[-1][1] + 1:
            runs[-1][1] = number
        else:
            runs.append([number, number])
    return ", ".join(str(first) if first == last else f"{first}-{last}" for first, last in runs)


def _ci_phase(number, plan):
    """The phase `/ci <number>` starts: the epic of the test titled `Test <number>:`, else the phase whose range holds
    the number. None when that gives no single phase, as for a title outside every epic's directory."""
    found = {plan.epics.get(epic) for titled, epic in plan.titled if titled == number}
    found = found or {phase for phase, numbers in plan.ranges.items() if number in numbers}
    return found.pop() if len(found) == 1 else None


def _traps(signal, script=INTEGRATION):
    """(line index, match) of each trap ``script`` sets for ``signal``."""
    lines = script.read_text().splitlines()
    return [(i, m) for i, line in enumerate(lines) if (m := _TRAP.fullmatch(line.strip())) and m["signal"] == signal]


def _trap_in_effect(lines, index, signal):
    """The last `trap ... <signal>` before lines[index] at its indentation, in its block: the one set when it runs."""
    indent = len(lines[index]) - len(lines[index].lstrip())
    for line in reversed(lines[:index]):
        level = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#") or level > indent:
            continue
        if level < indent:
            return None
        if re.fullmatch(rf"trap .+ {signal}", line.strip()):
            return line.strip()
    return None


def _top_level_start(lines, index):
    """Where lines[index] starts to run: the call of the function it is in, else the line itself."""
    functions = [i for i in range(index) if re.fullmatch(r"\w+\(\) \{", lines[i]) and lines.index("}", i) > index]
    if not functions:
        return index
    name = lines[functions[-1]].split("(")[0]
    return next(i for i, line in enumerate(lines) if re.fullmatch(rf"{name}\b(?!\().*", line))


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
    plan = {phase["phase"] for phase in cp.read_plan(TESTPLANS)}
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
    first_test = min(number for number, _ in _calls(lines, _RUN))
    first_section = min((number for number, _ in _calls(lines, "phase_section")), default=first_test)

    assert selection, "integration.sh must select the phase in a PHASE SELECTION section"
    checks = [line for _, line in selection.lines if line.startswith("if ") and _PHASE_REF.search(line)]
    exits = [number for number, line in selection.lines if _EXIT_ERROR.fullmatch(line)]
    assert checks and exits, "PHASE SELECTION must stop the script when $PHASE is not one of its phases"
    assert max(exits) < first_test
    assert first_section < first_test, "a test before the first phase_section belongs to no phase"
    assert not _DEFAULT_PHASE.search(INTEGRATION.read_text())


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
    assert [section.name for section in untagged if _calls(section.lines, _RUN)] == []


def test_each_phase_runs_its_sections_of_the_plan():
    """Regression b.aqj: no section had a phase, so Phases 1, 2 and 5 each ran every section, Phase 6's too."""
    runs = {}
    for section in _sections():
        if section.phase is not None and _calls(section.lines, _RUN):
            runs.setdefault(section.phase, set()).add(section.name)

    assert runs == PHASE_SECTIONS


# ---------------------------------------------------------------------------
# Test numbers: integration.sh and the plan's ranges and titles
# ---------------------------------------------------------------------------


def test_each_script_phase_range_is_the_tests_its_sections_run():
    """Regression b.6s5: Phase 2 ran tests 4-77 and 174-179 for its range 4-77, Phase 5 86-173 and 186-192 for 78-149,
    Phase 6 78-85 and 180-185 for 150-159. The script's numbers stay below the Claude phases' numbers, so adding a
    script test renumbers no Claude test."""
    script, script_phases = _script_test_numbers(), _script_phases()
    plan = _plan_numbers()
    claude_starts = [numbers.start for phase, numbers in plan.ranges.items() if phase not in script_phases]

    expected = {phase: _spans(plan.ranges.get(phase, [])) for phase in script_phases}
    assert {phase: _spans(script.get(phase, [])) for phase in script_phases} == expected
    assert claude_starts and max(max(numbers) for numbers in script.values()) < min(claude_starts)


def test_each_claude_phase_range_is_its_titled_tests():
    """A Claude phase's tests are numbered only by their `Test <N>:` titles. Regression b.6s5: Phase 3 had tests
    104-114 and 133-135 for its range 104-114, Phase 4 115-126 and 136-138 for 115-126."""
    plan = _plan_numbers()
    claude = sorted(set(plan.ranges) - _script_phases())
    titled = {phase: [number for number, epic in plan.titled if plan.epics.get(epic) == phase] for phase in claude}

    assert claude
    assert {phase: _spans(numbers) for phase, numbers in titled.items()} == {p: _spans(plan.ranges[p]) for p in claude}


def test_every_claude_phase_test_area_has_test_cases():
    """/release-test runs only the test cases (t3) of a Claude phase's Test Areas: a Test Area without any runs
    nothing, whatever its own body describes. Regression b.ock: Phase 4's t2.qi9.4u.bb described its test in its body
    and had no test case. A script phase's t2 bees describe the script's tests themselves, so they need none."""
    areas = _claude_test_areas()

    assert areas and all(areas.values()), "Claude phases with no Test Area"
    empty = sorted(area for phase in areas.values() for area, cases in phase.items() if not cases)
    assert empty == [], "Test Areas with no test case"


def test_every_claude_phase_test_case_is_numbered_in_its_phase_range():
    """`/release-test <N>` and `/ci <N>` find a test only by its `Test <N>:` title, and the range must cover every
    test the phase runs. Regression b.ock: the six Body File tests of Phase 3 and of Phase 4 had no number, and the
    ranges (301-314, 315-329) left them out; the range check above sees only the tests that have a title."""
    plan = _plan_numbers()
    cases = {phase: [case for area in areas.values() for case in area] for phase, areas in _claude_test_areas().items()}

    untitled = sorted(case.id for phase_cases in cases.values() for case in phase_cases if case.number is None)
    assert untitled == [], "test cases with no `Test <N>:` title"
    numbers = {phase: _spans(case.number for case in phase_cases) for phase, phase_cases in cases.items()}
    assert numbers == {phase: _spans(plan.ranges[phase]) for phase in cases}


def test_claude_phase_test_numbers_follow_up_dependencies():
    """/release-test runs a phase's tests in up_dependencies order, and `/release-test <N>` runs N's up_dependencies
    first and skips the other tests before N, so a test's number is above those of its up_dependencies, tests of its
    own Test Area: /release-test looks for them in N's Test Area only. Bug b.ock numbered each phase's Body File tests
    in their up_dependencies order."""
    wrong = []
    for areas in _claude_test_areas().values():
        for cases in areas.values():
            numbers = {case.id: case.number for case in cases}
            wrong += [
                (case.id, case.number, dep, numbers.get(dep))
                for case in cases
                for dep in case.up
                if None in (case.number, numbers.get(dep)) or numbers[dep] >= case.number
            ]

    # An up_dependency outside the test case's Test Area has no number here (None)
    assert wrong == [], "(test case, its number, up_dependency, its number in that Test Area): not numbered above it"


def test_only_claude_phase_tests_carry_title_numbers_each_once():
    """A script phase's numbers live only in its range, so a script test added or removed renumbers no title.
    Regression b.6s5: `Test 150:` titled a Phase 6 test while Phase 5 ran test 150."""
    plan = _plan_numbers()
    script_phases = _script_phases()
    titles = Counter(number for number, _ in plan.titled)

    assert [number for number, count in titles.items() if count > 1] == [], "numbers in more than one title"
    titled_script_tests = [(number, epic) for number, epic in plan.titled if plan.epics.get(epic) in script_phases]
    assert titled_script_tests == [], "script-phase test bees titled `Test <N>:`"


def test_ci_starts_the_phase_that_runs_the_test():
    """/ci <N> starts the phase of the test titled `Test <N>:`, else the phase whose range holds N. Regression b.6s5:
    `/ci 150` started Phase 6 for Phase 5's test 150, and `/ci 175` and `/ci 182` started no phase."""
    plan = _plan_numbers()
    script_phases = _script_phases()
    # Each test number: the phases that run it. The script's phases run its tests, a Claude phase its titled tests
    runs = {}
    for phase, numbers in _script_test_numbers().items():
        for number in numbers:
            runs.setdefault(number, set()).add(phase)
    for number, epic in plan.titled:
        # A title outside every epic's directory is a test no phase runs: /ci finds the title, then no epic
        phases = runs.setdefault(number, set())
        if epic in plan.epics and plan.epics[epic] not in script_phases:
            phases.add(plan.epics[epic])
    started = {number: _ci_phase(number, plan) for number in sorted(runs)}

    assert runs
    wrong = {number: (phase, runs[number]) for number, phase in started.items() if {phase} != runs[number]}
    assert wrong == {}, "test number: (phase /ci starts, phases that run the test)"


# ---------------------------------------------------------------------------
# integration.sh: a start test number and the setup tests the tests from it on need
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    """Runs _replay_script as `PHASE=<phase> integration.sh <start>`: its result, and the (number, function) of each
    test that ran, in order."""
    script = tmp_path_factory.mktemp("replay") / "replay.sh"
    script.write_text(_replay_script())

    def run(phase, start):
        env = {**os.environ, "PHASE": str(phase)}
        result = subprocess.run(["bash", str(script), str(start)], env=env, capture_output=True, text=True, timeout=30)
        return result, [(int(number), fn) for number, fn in _PASSED.findall(result.stdout)]

    return run


@pytest.mark.parametrize(
    "start, setup",
    [
        # Bug b.m4k's starts: /ci 182, then /ci 189, 190 and 192
        pytest.param("test_ref_multi_entry", ["test_ref_setup"], id="ref_multi_entry"),
        pytest.param("test_p6_unset_resolver", ["test_p6_register_resolver_verify"], id="p6_unset_resolver"),
        pytest.param("test_p6_colonize_allowed_resolvers", ["test_p6_register_resolver_verify"], id="p6_colonize"),
        pytest.param("test_p6_reject_unset_referenced_resolver", ["test_p6_register_resolver_verify"], id="p6_reject"),
        # The section after REFERENCE MATERIALS needs none of its setup tests
        pytest.param("test_update_config", [], id="update_config"),
        # BODY FILE creates its tickets in TICKET CRUD's hive, ID CHARSET AND HIERARCHICAL IDS in ERROR HANDLING's
        pytest.param("test_body_file_update", ["test_crud_setup", "test_body_file_create"], id="body_file_update"),
        pytest.param("test_id_3level_bidir", ["test_error_setup"], id="id_3level_bidir"),
    ],
)
def test_a_start_inside_a_section_runs_the_setup_tests_it_needs_first(replay, start, setup):
    """Regression b.m4k: `/ci 182` skipped test_ref_setup (179), and `/ci 189`, 190 and 192 skipped
    test_p6_register_resolver_verify (187), so the tests after them ran against a hive or resolver never set up."""
    tests = {test.fn: test for test in _script_tests()}
    first = tests[start]
    result, ran = replay(first.phase, first.number)

    assert result.returncode == 0, result.stderr
    assert [fn for number, fn in ran if number < first.number] == setup
    assert ran[len(setup)] == (first.number, start), "the setup tests run before the start test"
    # They count as tests that ran
    assert f"Tests passed: {len(ran)} / {len(ran)}" in result.stdout


def test_each_start_number_runs_the_setup_tests_of_its_section_first(replay):
    """Bug b.m4k, for every section and every start number in it: first the setup tests of its section numbered below
    it, and those its phase keeps for later sections too (run_phase_setup_test), in test order under their own
    numbers, then every test of the phase from it on. No other test runs: a section none of whose tests run needs
    none of its setup tests, and no test of another phase runs (regression b.aqj: run_test skipped only the tests
    below START_TEST, whatever their phase)."""
    tests = _script_tests()
    unmarked = [test.fn for test in tests if test.fn.endswith("_setup") and test.hold is None]
    assert unmarked == [], "tests named *_setup run with run_test: a start number after them skips them"

    wrong = {}
    for start in tests:
        phase = [test for test in tests if test.phase == start.phase]
        held = [t for t in phase if t.hold == "phase" or (t.hold and t.section == start.section)]
        expected = [(t.number, t.fn) for t in held if t.number < start.number]
        expected += [(t.number, t.fn) for t in phase if t.number >= start.number]
        result, ran = replay(start.phase, start.number)
        if result.returncode or ran != expected:
            wrong[start.number] = (_spans(number for number, _ in ran), _spans(number for number, _ in expected))
    assert wrong == {}, "start number: (tests that ran, tests that should run; the same: ran out of order)"


def test_a_start_past_the_phases_last_test_runs_no_test_and_fails(replay):
    """With START_TEST past a phase's last test no test of it ran, and the phase still passed. Bug b.m4k: the setup
    tests still held then (test_crud_setup and test_error_setup, held to the end of their phase, and RESOLVER
    REGISTRY's, the last section) must not run either: they run only right before a test numbered START_TEST or
    above."""
    assert any(test.hold == "phase" for test in _script_tests()), "no setup test is held to the end of its phase"

    wrong = {}
    for phase, numbers in _script_test_numbers().items():
        result, ran = replay(phase, max(numbers) + 1)
        passed = f"RELEASE TEST PHASE {phase} PASSED" in result.stdout
        if result.returncode != 1 or ran or "[SETUP]" in result.stdout or passed:
            wrong[phase] = (result.returncode, result.stdout[-300:])
    assert wrong == {}, "phase: (exit status, end of its output)"


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


def test_tests_passed_line_counts_tests_not_checks():
    """Regression b.6s5: pass_test counted passed checks, and a test may pass several, so `Tests passed: X / Y` could
    show more passes than the Y tests that ran. run_numbered_test, which runs every test that runs, counts a test that
    returns: every failure ends the script."""
    body = [line.strip() for line in _function_body("run_numbered_test")]
    call = body.index('"$fn"')
    counted = [line for line in body[call + 1 :] if "PASS_COUNT" in line]
    code = [line.strip() for line in INTEGRATION.read_text().splitlines() if not line.lstrip().startswith("#")]
    uses = [line for line in code if "PASS_COUNT" in line]

    assert len(counted) == 1 and counted[0].startswith("PASS_COUNT="), "count the test after it returns"
    assert uses == ["PASS_COUNT=0", *counted, 'echo "Tests passed: $PASS_COUNT / $RUN_COUNT"']


def test_fail_test_ends_in_a_bug_filing_line_when_file_bug_py_prints_none():
    """file_bug.py prints BUG FILED: or BUG FILING FAILED:, unless it crashes first (e.g. on an import): then /ci
    saw a bare crash, not a failed test whose bug was not filed."""
    body = [line.strip() for line in _function_body("fail_test")]
    filing = next(i for i, line in enumerate(body) if "file_bug.py" in line)
    failed = next(i for i, line in enumerate(body) if "RELEASE TEST PHASE" in line)
    fallback = [i for i, line in enumerate(body) if line.startswith('echo "BUG FILING FAILED: ')]

    assert len(fallback) == 1 and filing < fallback[0] < failed
    # Only when file_bug.py's output has neither line
    condition = body[fallback[0] - 1]
    pattern = re.search(r"grep -q?E '([^']+)'", condition)
    assert condition.startswith("if ! ") and "$bug_out" in condition and pattern, condition
    outputs = {"BUG FILED: b.x7k": True, "Traceback\nBUG FILING FAILED: no hive": True, "ImportError: x": False}
    assert {out: bool(re.search(pattern[1], out, re.M)) for out in outputs} == outputs


# ---------------------------------------------------------------------------
# integration.sh: an error outside the assert helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "signal, guard",
    [
        pytest.param("ERR", [], id="ERR"),
        # A status of 128 and above is a signal from outside (e.g. the session closing), not a test failure
        pytest.param("EXIT", [r'\$\{?status\}?"? -lt 128\b'], id="EXIT"),
    ],
)
def test_an_error_outside_the_checks_fails_the_running_test(signal, guard):
    """Regression b.mqm: under set -e, a command failing outside the assert helpers (test_http_port_config's `kill`
    of a server that had died) ended Phase 5 with no FAIL line and no bug. The ERR trap catches a failing command, the
    EXIT trap an error that ends the script without one (e.g. an unset variable under set -u)."""
    lines = INTEGRATION.read_text().splitlines()
    traps = _traps(signal)
    runner = [line.strip() for line in _function_body("run_numbered_test")]
    call = runner.index('"$fn"')

    assert len(traps) == 1, f"integration.sh must set one {signal} trap: setting another replaces it"
    [(at, trap)] = traps
    assert at < _first_test_index(lines) and not lines[at].startswith(" "), "set it before the first test"
    body = [line.strip() for line in _function_body(trap["handler"])]
    report = next((i for i, line in enumerate(body) if line.startswith('fail_test "$CURRENT_TEST"')), None)
    # As the assert helpers do (FAIL line, bug, RELEASE TEST PHASE N FAILED), only during a test, and only once
    assert report is not None, f"{trap['handler']} must report through fail_test"
    guards = [line for line in body[:report] if line.startswith("if ")]
    terms = [r"\$CURRENT_TEST", r"\$FAIL_COUNT", *guard]
    assert any(all(re.search(term, line) for term in terms) for line in guards), guards
    # With the ERR trap still set, a failure while reporting would report again
    assert "trap - ERR" in body[:report]
    # run_numbered_test, which runs every test, names it only while it runs: a failure between tests is no test's
    assert runner[call - 1 : call + 2] == ['CURRENT_TEST="$fn"', '"$fn"', 'CURRENT_TEST=""']


def test_err_trap_fires_in_the_tests_and_reports_from_the_main_shell_only():
    """Without set -E, bash runs no ERR trap inside a function, and every test is one. Subshells and command
    substitutions inherit it too: a report there would land in a captured output, and the failure reaches the main
    shell anyway, as the failure of the command that ran it."""
    lines = INTEGRATION.read_text().splitlines()
    errtrace = [i for i, line in enumerate(lines) if _ERRTRACE.fullmatch(line)]
    traps = _traps("ERR")

    assert errtrace and errtrace[0] < _first_test_index(lines), "set -E must come before the tests"
    assert len(traps) == 1
    [(_, trap)] = traps
    # The FAIL line says where the test stopped and which command failed
    assert {'"$LINENO"', '"$BASH_COMMAND"'} <= set(trap["args"].split()), trap[0]
    body = [line.strip() for line in _function_body(trap["handler"])]
    guard = next(i for i, line in enumerate(body) if line.startswith("if "))
    assert "$BASHPID" in body[guard] and "$$" in body[guard] and re.fullmatch(r"return(?: 0)?", body[guard + 1])
    assert all(line.startswith("local ") for line in body[:guard]), "nothing may print before the main-shell check"


@pytest.mark.parametrize(
    "script, signal, arguments, first",
    [
        pytest.param(INTEGRATION, "ERR", ['"$?"'], 'local status="$1"', id="integration_sh_ERR"),
        pytest.param(INTEGRATION, "EXIT", [], "local status=$?", id="integration_sh_EXIT"),
        pytest.param(TEST_RUNNER, "ERR", ['"$?"'], 'local status="$1"', id="test_runner_sh_ERR"),
    ],
)
def test_trap_handler_takes_the_failing_status_first(script, signal, arguments, first):
    """Each command run before $? is read resets it, and the report would give that command's status. An ERR trap
    hands it to its handler as the first argument."""
    [(_, trap)] = _traps(signal, script)
    body = [line.strip() for line in _function_body(trap["handler"], script) if not line.lstrip().startswith("#")]

    assert trap["args"].split()[:1] == arguments, trap[0]
    assert body[0] == first


# ---------------------------------------------------------------------------
# test_runner.sh: a failing setup command
# ---------------------------------------------------------------------------


def test_test_runner_names_a_failing_setup_command():
    """Regression b.mqm: under set -e, a failing setup command (a `claude mcp add`, say) ended the phase with only
    entrypoint.sh's TEST RUNNER EXITED (status N): no reason. The ERR trap prints the crash line, naming the command."""
    lines = TEST_RUNNER.read_text().splitlines()
    traps = _traps("ERR", TEST_RUNNER)
    first_setup = min(i for i, line in enumerate(lines) if re.match(r"\s*(?:claude|bees|python3)\s", line))

    assert len(traps) == 1
    [(at, trap)] = traps
    assert not lines[at].startswith(" ") and at < first_setup, "set it before the first setup command"
    assert '"$BASH_COMMAND"' in trap["args"].split(), trap[0]
    body = [line.strip() for line in _function_body(trap["handler"], TEST_RUNNER) if not line.lstrip().startswith("#")]
    crash = [i for i, line in enumerate(body) if line.startswith('echo "TEST RUNNER EXITED: ')]
    # Then exits with the failing command's status: never 0, as the trap fires only on a failure
    assert crash and crash[-1] < len(body) - 1 and re.fullmatch(r'exit "?\$\{?status\}?"?', body[-1]), body


@pytest.mark.parametrize(
    "start",
    [
        pytest.param(r"\s*exec bash \S*tests/integration\.sh\b.*", id="integration_sh"),
        # `claude mcp` only registers a server
        pytest.param(r"\s*(?:exec\s+)?claude\s+(?!mcp\b).*", id="claude_run"),
    ],
)
def test_test_runner_clears_the_setup_trap_before_the_tests_start(start):
    """integration.sh and the Claude run report their own ends. A Claude run without a result line returns 1: with
    the trap still set, a second crash line would call that a setup failure."""
    lines = TEST_RUNNER.read_text().splitlines()
    starts = [i for i, line in enumerate(lines) if re.fullmatch(start, line)]

    assert len(starts) == 1, [lines[i] for i in starts]
    assert _trap_in_effect(lines, _top_level_start(lines, starts[0]), "ERR") == "trap - ERR"


@pytest.mark.parametrize("script", [INTEGRATION, TEST_RUNNER], ids=lambda path: path.name)
def test_script_parses(script):
    """`bash -n` parses without running anything."""
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stderr
