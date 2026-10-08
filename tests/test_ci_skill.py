"""
Tests for how /ci reads the test plan and records phase statuses: docker/ci_plan.py, and static
consistency checks between the /ci skill and the testplans hive it drives.

PURPOSE:
/ci (.claude/skills/ci/SKILL.md) reads and sets the status of the phase epics under the
testplans bee. The containers run this checkout's copy of the plan (docker/testplans), so /ci
reads that copy from its files (docker/ci_plan.py) and writes statuses only through a hive that
bees resolves to that same copy, never by name. bees rejects any status the hive does not allow,
so every status the skill uses must be listed in docker/testplans/.hive/identity.json.

SCOPE - Tests that belong here:
- ci_plan.py: the phases it reads (children order, frontmatter as PyYAML reads it, unreadable
  plans), the status hive it picks from `bees list-hives` output, and its command line
- the skill reads the plan through ci_plan.py and writes statuses only with `bees update-ticket --hive`
- statuses the /ci skill sets or reads on testplans epics are allowed by the testplans hive
- the skill's run-scope rules cover every status it sets
- the /ci and release-test skills run every phase of the plan, however many: neither builds in a
  fixed set of phase numbers (only /ci's gatekeeper, Phase 1, is named)

SCOPE - Tests that DON'T belong here:
- CI port and bees server identity check -> test_check_bees_server.py
- phase deadline and the result signals /ci polls for -> test_check_bees_server.py
- scope matching ci_plan.py shares with the bugs hive choice -> test_ci_bug_filing.py
- status_values validation inside bees -> test_set_status_values.py
- which runner runs each phase, and the sections integration.sh runs per phase -> test_integration_phases.py
"""

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from src.config import get_scoped_config
from src.writer import serialize_frontmatter
from tests.conftest import write_multi_scope_config
from tests.helpers import load_script, write_ticket_file

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_SKILL = REPO_ROOT / ".claude" / "skills" / "ci" / "SKILL.md"
RELEASE_TEST_SKILL = REPO_ROOT / ".claude" / "skills" / "release-test" / "SKILL.md"
TESTPLANS = REPO_ROOT / "docker" / "testplans"
TESTPLANS_IDENTITY = TESTPLANS / ".hive" / "identity.json"
CI_PLAN = REPO_ROOT / "docker" / "ci_plan.py"

cp = load_script(CI_PLAN)

# One or more inline-code words: "`failed`", "`failed` or `pupa`", "`finished`/`legendary`"
_CODE_WORDS = r"(`[\w-]+`(?:\s*(?:,|/|or)\s*`[\w-]+`)*)"

# "Set epic status to `failed`", "Set ALL epic statuses to `legendary`", "reset all to `pupa`", "marked `finished`"
_SETS_STATUS = re.compile(r"\b(?:(?:status(?:es)?|reset)\b[^`\n]*?\bto|marked)\s+" + _CODE_WORDS, re.IGNORECASE)
# Run-scope list: "- `failed` or `pupa` = needs to run."
_RUN_SCOPE_ITEM = re.compile(r"^\s*[-*]\s+" + _CODE_WORDS + r"\s*=", re.MULTILINE)
# Phase numbers listed together or as a range: "phase to run (1, 2, 3, or 4)", "Phase 3/4", "Phases 1 & 2",
# "phases 3 and 4", "Phase 3 and Phase 4", "phases (1-4)", "Phases 1–4", "phases 2 through 6"
_PHASE_LIST = re.compile(
    r"\bphases?\b[^.\n]{0,40}?\b\d+"
    r"(?:(?:\s*[-–—,/&]\s*(?:(?:or|and)\s+)?|\s+(?:or|and|to|through)\s+)(?:phases?\s+)?\d+\b)+",
    re.IGNORECASE,
)


def _statuses(pattern, text):
    return {word for fragment in pattern.findall(text) for word in re.findall(r"`([\w-]+)`", fragment)}


def _yaml_frontmatter(path):
    """A ticket file's frontmatter as PyYAML reads it."""
    return yaml.safe_load(path.read_text().split("---\n", 2)[1])


def _write_plan(testplans, epics, children=None):
    """Write plan b.qi9 into ``testplans``, with epics {id: (title, status)}; children default to the epics' order."""
    children = [*epics] if children is None else children
    write_ticket_file(testplans, cp.PLAN_ID, title="Full Regression Test", status="pupa", children=children)
    for epic_id, (title, status) in epics.items():
        write_ticket_file(testplans / cp.PLAN_ID, epic_id, title=title, type="t1", status=status, parent=cp.PLAN_ID)


# ---------------------------------------------------------------------------
# ci_plan: reading the plan
# ---------------------------------------------------------------------------


def test_read_plan_lists_phases_in_children_order(tmp_path):
    """Phase N is the plan's Nth child epic, whatever order the epic directories sort in."""
    _write_plan(
        tmp_path,
        {
            "t1.qi9.zz": ("Phase 1: Installation", "finished"),
            "t1.qi9.aa": ("Phase 2: CLI", "failed"),
            "t1.qi9.mm": ("Phase 3: Stdio", "pupa"),
        },
    )

    assert cp.read_plan(tmp_path) == [
        {"phase": 1, "id": "t1.qi9.zz", "title": "Phase 1: Installation", "status": "finished"},
        {"phase": 2, "id": "t1.qi9.aa", "title": "Phase 2: CLI", "status": "failed"},
        {"phase": 3, "id": "t1.qi9.mm", "title": "Phase 3: Stdio", "status": "pupa"},
    ]


@pytest.mark.parametrize(
    "epics, children",
    [
        pytest.param(None, None, id="no_plan"),
        pytest.param({}, [], id="no_child_epics"),
        pytest.param({"t1.qi9.aa": ("Phase 1: Installation", "pupa")}, ["t1.qi9.aa", "t1.qi9.bb"], id="missing_epic"),
        # Not a ticket ID but a path, to an epic file outside the plan: never read
        pytest.param({}, ["{outside}"], id="child_id_is_a_path"),
    ],
)
def test_read_plan_rejects_a_plan_it_cannot_read(tmp_path, epics, children):
    testplans = tmp_path / "testplans"
    testplans.mkdir()
    outside = write_ticket_file(tmp_path / "outside", "t1.qi9.aa", title="Phase 1: Elsewhere", type="t1")
    if epics is not None:
        _write_plan(testplans, epics, [child.format(outside=outside.with_suffix("")) for child in children])

    with pytest.raises(cp.PlanError):
        cp.read_plan(testplans)


_LONG = "a title long enough that the YAML writer wraps it onto a second line, " * 2


@pytest.mark.parametrize(
    "frontmatter",
    [
        # How bees writes tickets (src/writer.py): quoted where YAML needs it, null, block lists
        pytest.param(
            serialize_frontmatter(
                {"title": "Phase 1: It's 'quoted'", "status": "finished", "parent": None, "children": ["t2.a", "t2.b"]}
            ),
            id="single_quoted_null_and_list",
        ),
        # A nested field sends bees' writer to yaml.dump, which wraps long values onto a second line
        pytest.param(
            serialize_frontmatter({"title": f"Phase 1: {_LONG}", "status": "pupa", "egg": {"key": 1}}),
            id="long_quoted_title_on_two_lines",
        ),
        pytest.param(
            serialize_frontmatter({"title": f"Phase 1 {_LONG}".strip(), "status": "pupa", "egg": {"key": 1}}),
            id="long_plain_title_on_two_lines",
        ),
        # Other YAML forms of the same values
        pytest.param('---\ntitle: "Phase 1: \\"quoted\\" caf\\u00e9"\nparent: ~\n---\n', id="double_quoted_and_tilde"),
        pytest.param("---\nchildren:\n  - t2.a\n  - 't2.b'\nstatus: pupa\n---\n", id="indented_list_quoted_item"),
    ],
)
def test_read_frontmatter_reads_the_plan_fields_as_yaml_does(tmp_path, frontmatter):
    """ci_plan.py is stdlib-only, so it reads frontmatter itself: for the fields the plan needs, as PyYAML would."""
    path = tmp_path / "ticket.md"
    path.write_text(frontmatter + "\nBody text.\n")
    expected = _yaml_frontmatter(path)

    read = cp.read_frontmatter(path)

    fields = {"title", "status", "parent", "children"} & expected.keys()
    assert {field: read.get(field) for field in fields} == {field: expected[field] for field in fields}


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Phase 1: Installation\n", id="no_frontmatter"),
        pytest.param("---\ntitle: 'Phase 1: Installation'\nstatus: pupa\n", id="frontmatter_not_closed"),
    ],
)
def test_read_frontmatter_rejects_a_file_without_frontmatter(tmp_path, text):
    path = tmp_path / "ticket.md"
    path.write_text(text)

    with pytest.raises(cp.PlanError):
        cp.read_frontmatter(path)


# ---------------------------------------------------------------------------
# ci_plan: the status hive
# ---------------------------------------------------------------------------


@pytest.fixture
def plan_copies(tmp_path, monkeypatch):
    """This checkout's testplans copy and another checkout's, under tmp_path; .roots and .paths by role."""
    repos = tmp_path / "repos"
    repo = repos / "bees"
    own, other = repo / "docker" / "testplans", repos / "main" / "docker" / "testplans"
    for copy in (own, other):
        _write_plan(copy, {"t1.qi9.aa": ("Phase 1: Installation", "pupa")})
    (repo / "features").mkdir()
    (tmp_path / "own_link").symlink_to(own)
    monkeypatch.chdir(repo)  # from here, the relative path docker/testplans leads to this checkout's copy
    paths = {
        "own": str(own),
        "other": str(other),
        "own_link": str(tmp_path / "own_link"),
        "features": str(repo / "features"),
        "relative": "docker/testplans",
    }
    return SimpleNamespace(roots={"repo": str(repo), "repos": str(repos)}, paths=paths)


@pytest.mark.parametrize(
    "scopes, expected, reason_names",
    [
        pytest.param({"{repo}": {"plans": "own", "testplans": "features"}}, "plans", [], id="own_copy_under_any_name"),
        pytest.param({"{repo}": {"plans": "own_link"}}, "plans", [], id="own_copy_through_symlink"),
        pytest.param({"{repo}": {"testplans": "other"}}, None, ["other"], id="other_copy_only"),
        pytest.param(
            {"{repos}/**": {"testplans": "other"}, "{repo}": {"testplans": "own"}},
            "testplans",
            [],
            id="most_specific_scope_wins",
        ),
        pytest.param(
            {"{repos}/**": {"testplans": "own"}, "{repo}": {"testplans": "other"}},
            None,
            ["other"],
            id="shadowed_by_more_specific_scope",
        ),
        pytest.param(
            {"{repos}/*": {"plans": "own"}, "{repo}": {"testplans": "other"}},
            "plans",
            [],
            id="inherited_scope_under_another_name",
        ),
        # Which of two equally specific definitions bees uses is not certain: not even the last one listed
        pytest.param(
            {"{repo}": {"testplans": "other"}, "{repo}/": {"testplans": "own"}},
            None,
            ["other"],
            id="ambiguous_equally_specific_scopes",
        ),
        # A queen repo's list holds every scope: those that do not match the repo root never count
        pytest.param(
            {"{repos}/main": {"testplans": "own"}, "{repo}": {"features": "features"}},
            None,
            [],
            id="queen_list_non_matching_scope",
        ),
        pytest.param({"{repos}/b*s": {"plans": "own"}}, "plans", [], id="glob_scope"),
        pytest.param({"{repo}": {"testplans": "relative"}}, None, [], id="relative_path"),
    ],
)
def test_find_status_hive_only_resolves_to_this_checkouts_copy(
    plan_copies, mock_global_bees_dir, scopes, expected, reason_names
):
    """Regression b.g76: /ci set statuses through the hive named testplans, often another checkout's copy."""
    scopes = {
        pattern.format(**plan_copies.roots): {name: plan_copies.paths[role] for name, role in hives.items()}
        for pattern, hives in scopes.items()
    }
    listed = [
        {"normalized_name": name, "display_name": name.title(), "path": path, "scope": pattern}
        for pattern, hives in scopes.items()
        for name, path in hives.items()
    ]
    own = plan_copies.paths["own"]

    hive, reason = cp.find_status_hive(listed, plan_copies.roots["repo"], Path(own))

    assert hive == expected, reason
    assert all(os.path.realpath(plan_copies.paths[role]) in reason for role in reason_names), reason
    if hive:
        # The hive /ci writes statuses through is one that bees, run from the repo root, resolves to this copy
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                pattern: {"hives": {name: {"path": path, "display_name": name} for name, path in hives.items()}}
                for pattern, hives in scopes.items()
            },
        )
        resolved = get_scoped_config(Path(plan_copies.roots["repo"])).hives[hive].path
        assert os.path.realpath(resolved) == os.path.realpath(own)


# ---------------------------------------------------------------------------
# ci_plan: command line
# ---------------------------------------------------------------------------


def _run_ci_plan(stdin, cwd):
    return subprocess.run(
        [sys.executable, str(CI_PLAN)], input=stdin, cwd=cwd, capture_output=True, text=True, timeout=30
    )


def test_ci_plan_script_reads_this_checkouts_plan(isolated_bees_env, cli_runner, tmp_path):
    """/ci pipes `bees list-hives`, run in the repo root, into the script: phases from these files, and the hive."""
    isolated_bees_env.hives["ci_plans"] = {"path": str(TESTPLANS), "display_name": "CI Plans"}
    isolated_bees_env.write_config()
    list_hives_output, _ = cli_runner(["list-hives"])
    plan_dir = TESTPLANS / cp.PLAN_ID
    children = _yaml_frontmatter(plan_dir / f"{cp.PLAN_ID}.md")["children"]
    epics = {epic: _yaml_frontmatter(plan_dir / epic / f"{epic}.md") for epic in children}

    result = _run_ci_plan(list_hives_output, tmp_path)

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["status_hive"] == "ci_plans", plan["status_hive_reason"]
    assert plan["phases"] == [
        {"phase": number, "id": epic, "title": fields["title"], "status": fields["status"]}
        for number, (epic, fields) in enumerate(epics.items(), start=1)
    ]


@pytest.mark.parametrize(
    "stdin, relayed",
    [
        pytest.param("", "", id="empty_stdin"),
        pytest.param(
            json.dumps({"status": "error", "error_type": "config_conflict", "message": "Config conflict detected"}),
            "Config conflict detected",
            id="list_hives_error",
        ),
    ],
)
def test_ci_plan_script_reads_the_plan_without_a_hive_list(tmp_path, stdin, relayed):
    """Without hives, /ci still runs the plan, recording nothing: the reason says why, with bees' own error."""
    result = _run_ci_plan(stdin, tmp_path)

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["phases"] and plan["status_hive"] is None
    assert relayed in plan["status_hive_reason"]


def test_ci_plan_script_fails_when_the_plan_cannot_be_read(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cp, "TESTPLANS_PATH", tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"status": "success", "hives": []})))

    assert cp.main() == 1
    out, err = capsys.readouterr()
    assert out == "" and err.strip()


# ---------------------------------------------------------------------------
# /ci skill (static checks)
# ---------------------------------------------------------------------------


def test_ci_skill_reads_the_plan_through_ci_plan_and_writes_statuses_only_through_its_hive():
    """Regression b.g76: /ci read and set the plan through bees tools, in whichever copy they found it."""
    skill = CI_SKILL.read_text()
    commands = [line.strip() for block in re.findall(r"```bash\n(.*?)```", skill, re.S) for line in block.splitlines()]
    status_writes = [command for command in commands if "update-ticket" in command]

    assert "bees list-hives | python3 docker/ci_plan.py" in commands
    assert not re.search(r"\b(show_ticket|update_ticket)\b|bees show-ticket", skill), "no plan reads or writes by tool"
    assert status_writes and all(re.search(r"--status\s+\S.*--hive\s+\S", c) for c in status_writes), status_writes


def test_ci_skill_statuses_are_allowed_by_testplans_hive():
    """Regression b.9qc: /ci set failed phase epics to `failed`, which the testplans hive rejected."""
    skill = CI_SKILL.read_text()
    set_statuses = _statuses(_SETS_STATUS, skill)
    read_statuses = _statuses(_RUN_SCOPE_ITEM, skill)
    allowed = set(json.loads(TESTPLANS_IDENTITY.read_text())["status_values"])

    assert set_statuses, f"found no statuses set in {CI_SKILL.name}; update _SETS_STATUS to match the skill"
    assert read_statuses, f"found no run-scope statuses in {CI_SKILL.name}; update _RUN_SCOPE_ITEM to match the skill"
    # Run-scope rules must cover every status the skill sets, so a line either pattern misses shows up as a mismatch
    assert set_statuses == read_statuses, (
        f"statuses set and run-scope statuses in {CI_SKILL.name} differ (missing run-scope rule, or a pattern "
        f"missed a line): set only {sorted(set_statuses - read_statuses)}, "
        f"run-scope only {sorted(read_statuses - set_statuses)}"
    )
    used = set_statuses | read_statuses
    assert used <= allowed, f"/ci uses statuses the testplans hive rejects: {sorted(used - allowed)}"


@pytest.mark.parametrize(
    "named",
    [
        pytest.param(r"run_test\.sh(?:[ \t]|\\\n)+(\S+)", id="launched_phase"),
        pytest.param(r"\bbees-ci-(\S+)", id="session"),
    ],
)
def test_ci_skill_names_no_phase_but_the_gatekeeper(named):
    """Regression b.f1z: /ci launched and polled Phases 2, 3 and 4 by number, so phases 5 and 6 never ran."""
    code = "".join(re.findall(r"```[^\n]*\n(.*?)```", CI_SKILL.read_text(), re.S))
    # A word with a number in it names that phase, however quoted or punctuated ("2", 3;); one without is the
    # placeholder (<N>, $N, ${N})
    phases = {phase for word in re.findall(named, code) for phase in re.findall(r"\d+", word) or ["<N>"]}

    # Phase 1 runs alone, first; every later phase, however many, runs the same command with its number filled in
    assert {"<N>"} <= phases <= {"1", "<N>"}, f"phases named in {CI_SKILL.name} commands: {sorted(phases)}"


def test_release_test_skill_lists_no_fixed_phases():
    """Regression b.f1z: the skill said the phase was 1, 2, 3, or 4, and the serve extra was for Phase 3/4."""
    assert _PHASE_LIST.findall(RELEASE_TEST_SKILL.read_text()) == []
