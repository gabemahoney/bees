"""
Tests for sanitize_hive on a hive that encloses another hive, and for fixes_applied matching disk (b.x6n).

PURPOSE:
A hive nested in another hive's directory (registered, or holding its own .hive/) belongs to that
hive alone: sanitizing the enclosing hive must not scan, fix, move or remove anything in it. Every
fix sanitize_hive lists in fixes_applied is on disk; a fix whose write fails is reported as a
fix_not_applied error instead.

SCOPE - Tests that belong here:
- _sanitize_hive() on the enclosing hive: no moves, errors or fixes for the nested hive, its files unchanged
- Linter directory enforcement and empty ticket dir cleanup on the enclosing hive, including a move whose
  target directory is, or holds, another hive, and one whose ticket directory holds another hive
- fixes_applied against disk: failed writes, no rewrite of a ticket whose write failed, a fix to a misplaced ticket
- A non-integer priority: reported in errors_remaining, never auto-fixed (b.1zh)

SCOPE - Tests that DON'T belong here:
- Walker pruning (walk_hive, iter_ticket_files*, find_ticket_file, find_*_hive_root) -> test_paths.py
- General linter rules and other sanitize_hive behavior -> test_linter.py
"""

import json
import os
import time
from pathlib import Path

import pytest

import src.linter
from src.linter import Linter
from src.linter_report import LinterReport
from src.mcp_hive_ops import _sanitize_hive, write_identity
from src.reader import read_ticket
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import INVALID_PRIORITY_FRONTMATTER

# Tickets of the nested hive built by the nested_hives fixture
NESTED_IDS = ["b.ppp", "t1.ppp.ab", "t2.ppp.ab.cd", "t3.ppp.ab.cd.ef", "b.qqq"]
# (subdir of Ideas/, ticket ID, fields): bee b.par in place, its child t1.par.aa misplaced under Ideas/misplaced/
MISPLACED_CHILD = [
    ("", "b.par", {"children": ["t1.par.aa"]}),
    ("misplaced", "t1.par.aa", {"type": "t1", "parent": "b.par"}),
]


def _files(directory: Path) -> dict[str, bytes]:
    """Every file below directory, by relative path, with its bytes."""
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def _find_ticket_file_unpruned(hive_root: Path, ticket_id: str, deep: bool = False) -> Path | None:
    """Stand-in for find_ticket_file whose walk, like the one before b.x6n, enters nested hives."""
    for dirpath, dirs, files in os.walk(hive_root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if os.path.basename(dirpath) == ticket_id and f"{ticket_id}.md" in files:
            return Path(dirpath) / f"{ticket_id}.md"
    return None


@pytest.fixture(params=["registered", "registered_without_marker", "unregistered_with_marker"])
def enclosing_hive(request, tmp_path, monkeypatch, mock_global_bees_dir):
    """Hive `ideas` (tier t1) at Ideas/; yields (Ideas, nest), where nest(root, name) makes root another hive."""
    monkeypatch.chdir(tmp_path)
    ideas = tmp_path / "Ideas"
    hives = {"ideas": {"path": str(ideas), "display_name": "Ideas"}}

    def write_config():
        scope = {"hives": hives, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope, hive_child_tiers={"ideas": {"t1": ["Doc", "Docs"]}})

    def nest(root: Path, name: str):
        if request.param != "unregistered_with_marker":
            hives[name] = {"path": str(root), "display_name": name.title()}
            write_config()
        if request.param != "registered_without_marker":
            (root / ".hive").mkdir(parents=True)
            identity = {"normalized_name": name, "display_name": name.title(), "created_at": "2026-02-05T00:00:00"}
            tiers = {"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"], "t3": ["Subtask", "Subtasks"]}
            write_identity(root / ".hive", {**identity, "child_tiers": tiers})

    write_config()
    with repo_root_context(tmp_path):
        yield ideas, nest


@pytest.fixture
def nested_hives(enclosing_hive):
    """Hive `plans` (tiers t1-t3) nested at Ideas/Plans/ in hive `ideas`, tickets in both; returns both paths."""
    ideas, nest = enclosing_hive
    plans = ideas / "Plans"
    nest(plans, "plans")

    # ideas: b.aaa depends on b.bbb, which lacks the backlink, so sanitize has one fix to write
    write_ticket_file(ideas, "b.aaa", up_dependencies=["b.bbb"])
    write_ticket_file(ideas, "b.bbb")
    # plans: a bee with a t1 -> t2 -> t3 subtree
    write_ticket_file(plans, "b.ppp", children=["t1.ppp.ab"])
    write_ticket_file(plans / "b.ppp", "t1.ppp.ab", type="t1", parent="b.ppp", children=["t2.ppp.ab.cd"])
    t1_dir = plans / "b.ppp" / "t1.ppp.ab"
    write_ticket_file(t1_dir, "t2.ppp.ab.cd", type="t2", parent="t1.ppp.ab", children=["t3.ppp.ab.cd.ef"])
    write_ticket_file(t1_dir / "t2.ppp.ab.cd", "t3.ppp.ab.cd.ef", type="t3", parent="t2.ppp.ab.cd")
    # A missing backlink inside plans: only plans' own sanitize may fix it
    write_ticket_file(plans, "b.qqq", up_dependencies=["b.ppp"])
    return ideas, plans


class TestSanitizeEnclosingHive:
    """Sanitizing a hive never touches a hive nested inside its directory."""

    async def test_nested_hive_left_untouched(self, nested_hives):
        """No moves, errors or fixes for the nested hive, its files byte-identical; the one fix listed is on disk."""
        ideas, plans = nested_hives
        plans_before = _files(plans)

        result = await _sanitize_hive("ideas")

        assert result["errors_remaining"] == []
        assert [(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"]] == [("b.bbb", "add_down_dependency")]
        assert read_ticket("b.bbb", file_path=ideas / "b.bbb" / "b.bbb.md").down_dependencies == ["b.aaa"]
        assert _files(plans) == plans_before
        assert sorted(p.name for p in ideas.iterdir()) == [".hive", "Plans", "b.aaa", "b.bbb"]

    def test_empty_dir_cleanup_skips_nested_hive(self, nested_hives):
        """An old empty ticket dir of the enclosing hive is removed; one in the nested hive is kept."""
        ideas, plans = nested_hives
        own, nested = ideas / "b.eee", plans / "b.fff"
        for empty_dir in (own, nested):
            empty_dir.mkdir()
            os.utime(empty_dir, (time.time() - 1200,) * 2)
        report = LinterReport()

        Linter(str(ideas), hive_name="ideas", auto_fix=True).detect_empty_ticket_dirs(report)

        assert [(f.ticket_id, f.fix_type) for f in report.fixes] == [("b.eee", "remove_empty_dir")]
        assert not own.exists()
        assert nested.exists()

    def test_directory_enforcement_never_moves_across_nested_hive(self, nested_hives, monkeypatch):
        """Even when ticket lookup reaches into the nested hive, no ticket is moved out of or into it."""
        ideas, _plans = nested_hives
        # An enclosing-hive ticket whose parent bee lives in the nested hive
        write_ticket_file(ideas, "t1.ppp.zz", type="t1", parent="b.ppp")
        ticket_ids = ["b.aaa", "b.bbb", "t1.ppp.zz", *NESTED_IDS]
        tickets = [read_ticket(tid, file_path=_find_ticket_file_unpruned(ideas, tid)) for tid in ticket_ids]
        monkeypatch.setattr("src.linter.find_ticket_file", _find_ticket_file_unpruned)
        before = _files(ideas)
        report = LinterReport()

        Linter(str(ideas), hive_name="ideas", auto_fix=True).enforce_directory_structure(tickets, report)

        assert report.fixes == []
        blocked = {e.ticket_id for e in report.get_errors(error_type="cross_hive_move_blocked")}
        assert blocked == {"b.ppp", "b.qqq", "t1.ppp.zz"}
        assert _files(ideas) == before

    @pytest.mark.parametrize(
        "tickets,nested_root,blocked",
        [
            pytest.param([("misplaced", "b.abc", {})], "b.abc", "b.abc", id="bee_onto_nested_root"),
            pytest.param([("misplaced", "b.def", {})], "b.def/sub", "b.def", id="bee_onto_dir_holding_nested_hive"),
            pytest.param(MISPLACED_CHILD, "b.par/t1.par.aa", "t1.par.aa", id="child_onto_nested_root"),
            pytest.param(
                [("misplaced", "b.car", {})], "misplaced/b.car/sub/deeper", "b.car", id="bee_carrying_nested_hive"
            ),
            pytest.param(
                MISPLACED_CHILD, "misplaced/t1.par.aa/sub/deeper", "t1.par.aa", id="child_carrying_nested_hive"
            ),
        ],
    )
    async def test_move_never_replaces_or_carries_nested_hive(self, enclosing_hive, tickets, nested_root, blocked):
        """A move onto a dir that is or holds another hive, or carrying one, is blocked; an ordinary move runs."""
        ideas, nest = enclosing_hive
        for subdir, ticket_id, fields in tickets:
            write_ticket_file(ideas / subdir, ticket_id, **fields)
        write_ticket_file(ideas / "misplaced", "b.okk")
        nest(ideas / nested_root, "nest")
        write_ticket_file(ideas / nested_root, "b.zzz")
        nested_before = _files(ideas / nested_root)

        result = await _sanitize_hive("ideas")

        errors = [(e["ticket_id"], e["error_type"]) for e in result["errors_remaining"]]
        assert errors == [(blocked, "cross_hive_move_blocked")]
        assert [(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"]] == [("b.okk", "move_directory")]
        assert (ideas / "b.okk" / "b.okk.md").exists()
        assert (ideas / "misplaced" / blocked / f"{blocked}.md").exists()
        assert _files(ideas / nested_root) == nested_before


class _AnyButNone:
    """Equal to any value but None: the value of a field the fix generates."""

    def __eq__(self, other):
        return other is not None

    def __repr__(self):
        return "<any value but None>"


# (fix_type, ticket the fix writes, tickets to create as (subdir, id, fields), field the fix sets, its value after)
FIX_CASES = [
    pytest.param(
        "add_child",
        "b.aaa",
        [("", "b.aaa", {}), ("b.aaa", "t1.aaa.bc", {"type": "t1", "parent": "b.aaa"})],
        "children",
        ["t1.aaa.bc"],
        id="add_child",
    ),
    pytest.param(
        "add_down_dependency",
        "b.bbb",
        [("", "b.aaa", {"up_dependencies": ["b.bbb"]}), ("", "b.bbb", {})],
        "down_dependencies",
        ["b.aaa"],
        id="add_down_dependency",
    ),
    pytest.param(
        "add_up_dependency",
        "b.bbb",
        [("", "b.aaa", {"down_dependencies": ["b.bbb"]}), ("", "b.bbb", {})],
        "up_dependencies",
        ["b.aaa"],
        id="add_up_dependency",
    ),
    pytest.param("add_guid", "b.aaa", [("", "b.aaa", {"guid": None})], "guid", _AnyButNone(), id="add_guid"),
    pytest.param(
        "remove_dangling_dependency",
        "b.aaa",
        [("", "b.aaa", {"up_dependencies": ["b.zzz"]})],
        "up_dependencies",
        [],
        id="remove_dangling_dependency",
    ),
    pytest.param(
        "clear_dangling_parent",
        "t1.zzz.bc",
        [("", "t1.zzz.bc", {"type": "t1", "parent": "b.zzz"})],
        "parent",
        None,
        id="clear_dangling_parent",
    ),
]


class TestFixesAppliedMatchDisk:
    """fixes_applied lists a fix only once its ticket is written."""

    @pytest.fixture
    def backend(self, isolated_bees_env):
        """Hive `backend` (tier t1) with auto_fix_dangling_refs on; returns its path."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})
        config_path = isolated_bees_env.global_bees_dir / "config.json"
        config_path.write_text(json.dumps({**json.loads(config_path.read_text()), "auto_fix_dangling_refs": True}))
        return hive_dir

    @pytest.mark.parametrize("write_fails", [pytest.param(False, id="written"), pytest.param(True, id="write_fails")])
    @pytest.mark.parametrize("fix_type,target,tickets,field,expected", FIX_CASES)
    async def test_fix_listed_only_when_written(
        self, backend, monkeypatch, fix_type, target, tickets, field, expected, write_fails
    ):
        """A written fix is listed and is on disk; a failed one is a fix_not_applied error, file unchanged."""
        for subdir, ticket_id, fields in tickets:
            write_ticket_file(backend / subdir, ticket_id, **fields)
        target_file = next(backend.rglob(f"{target}.md"))
        before = target_file.read_bytes()
        if write_fails:
            real_write = src.linter.write_ticket_file

            def write_or_fail(ticket_id, *args, **kwargs):
                if ticket_id == target:
                    raise OSError("simulated write failure")
                return real_write(ticket_id, *args, **kwargs)

            monkeypatch.setattr("src.linter.write_ticket_file", write_or_fail)

        result = await _sanitize_hive("backend")

        listed = (target, fix_type) in {(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"]}
        not_applied = [
            e for e in result["errors_remaining"] if e["error_type"] == "fix_not_applied" and e["ticket_id"] == target
        ]
        if write_fails:
            assert not listed
            assert len(not_applied) == 1
            assert fix_type in not_applied[0]["message"]
            assert target_file.read_bytes() == before
        else:
            assert listed
            assert not_applied == []
            assert getattr(read_ticket(target, file_path=target_file), field) == expected

    def test_ticket_whose_write_failed_is_not_written_again_in_run(self, backend, monkeypatch):
        """Once a ticket's write fails, its later fixes in the run are withdrawn too; the next run writes them all."""
        ccc = write_ticket_file(backend, "b.ccc", guid=None)
        write_ticket_file(backend, "b.ddd", up_dependencies=["b.ccc"])
        before = ccc.read_bytes()
        real_write = src.linter.write_ticket_file
        failed = []

        def fail_first_write(ticket_id, *args, **kwargs):
            if ticket_id == "b.ccc" and not failed:
                failed.append(ticket_id)
                raise OSError("simulated write failure")
            return real_write(ticket_id, *args, **kwargs)

        monkeypatch.setattr("src.linter.write_ticket_file", fail_first_write)
        linter = Linter(str(backend), hive_name="backend", auto_fix=True)

        report = linter.run()

        assert report.fixes == []
        not_applied = [e.message for e in report.get_errors(ticket_id="b.ccc", error_type="fix_not_applied")]
        assert len(not_applied) == 2
        assert "'add_guid'" in not_applied[0] and "'add_down_dependency'" in not_applied[1]
        assert ccc.read_bytes() == before

        report = linter.run()

        fixes = sorted((f.ticket_id, f.fix_type) for f in report.fixes)
        assert fixes == [("b.ccc", "add_down_dependency"), ("b.ccc", "add_guid")]
        assert report.get_errors(error_type="fix_not_applied") == []
        fixed = read_ticket("b.ccc", file_path=ccc)
        assert fixed.guid is not None
        assert fixed.down_dependencies == ["b.ddd"]

    async def test_fix_to_misplaced_ticket_lands_in_its_only_copy(self, backend):
        """A fix to a ticket outside its expected directory is written to that file, which is then moved."""
        write_ticket_file(backend, "b.aaa", up_dependencies=["b.bbb"])
        write_ticket_file(backend / "misc", "b.bbb")

        result = await _sanitize_hive("backend")

        fixes = {(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"]}
        assert fixes == {("b.bbb", "add_down_dependency"), ("b.bbb", "move_directory")}
        assert list(backend.rglob("b.bbb.md")) == [backend / "b.bbb" / "b.bbb.md"]
        assert read_ticket("b.bbb", file_path=backend / "b.bbb" / "b.bbb.md").down_dependencies == ["b.aaa"]


class TestInvalidPriority:
    """A non-integer priority is reported by sanitize_hive and left exactly as stored (b.1zh)."""

    @pytest.mark.parametrize("ticket_type,ticket_id", [("bee", "b.par"), ("t1", "t1.par.aa")])
    @pytest.mark.parametrize("raw,_,type_name", INVALID_PRIORITY_FRONTMATTER.values(), ids=list(INVALID_PRIORITY_FRONTMATTER))
    async def test_invalid_priority_remains_unfixed(self, isolated_bees_env, ticket_type, ticket_id, raw, _, type_name):
        """The invalid priority is in errors_remaining, the hive is corrupt, and the ticket file is unchanged."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})
        fields = {"raw_fields": {"priority": raw}}
        bee = write_ticket_file(hive_dir, "b.par", children=["t1.par.aa"], **(fields if ticket_type == "bee" else {}))
        task = write_ticket_file(hive_dir / "b.par", "t1.par.aa", type="t1", parent="b.par",
                                 **(fields if ticket_type == "t1" else {}))
        target = bee if ticket_type == "bee" else task
        before = target.read_bytes()

        result = await _sanitize_hive("backend")

        errors = [e for e in result["errors_remaining"] if e["ticket_id"] == ticket_id and "priority" in e["message"]]
        assert [e["error_type"] for e in errors] == ["invalid_field_type"]
        assert type_name in errors[0]["message"]
        assert result["is_corrupt"] is True
        assert target.read_bytes() == before
