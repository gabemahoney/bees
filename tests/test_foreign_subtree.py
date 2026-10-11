"""
Tests for foreign ticket subtrees: ticket trees inside a ticket's folder that are not part of the hive (b.94t).

PURPOSE:
A ticket's folder can hold arbitrary content, e.g. a test fixture with its own tickets (and no `.hive/`)
at `b.ai5/prefix-tree/tickets/testplans/`. The linter and sanitize-hive must not scan, fix, move or remove
anything in it: they report one `foreign_ticket_subtree` warning per subtree and leave every file as it is.
A ticket misplaced under a plain directory, or in an ancestor's directory, is still moved. A reference to
a ticket found only in a foreign subtree is reported and never cleared.

SCOPE - Tests that belong here:
- _sanitize_hive() and Linter.run() on a hive holding a foreign subtree: warning, scan, no moves or fixes
- Misplaced tickets of the hive still moved, also next to a foreign subtree and when a copy of their ID is in it
- Empty ticket dir cleanup that skips the foreign subtree, and a foreign subtree that moves with its owner
  (also when the move fails partway), and the warning naming the subtree where it ends up
- Parent lookups that skip the subtree, and dangling references to tickets found only in it (also from another hive)
- A directory with a copy of a settled ticket (foreign though another ticket in it looks related), and a ticket
  claimed by its settled parent's children list (not foreign)

SCOPE - Tests that DON'T belong here:
- find_foreign_subtrees() and the skip_dirs of walk_hive/find_ticket_file -> test_paths.py
- Nested hives (a `.hive/` or a registered hive root) -> test_sanitize_hive.py
- Directory enforcement without foreign subtrees -> test_linter_directory_enforcement.py
"""

import json
import os
import re
import time
from pathlib import Path

import pytest

from src.linter import Linter, TicketScanner
from src.mcp_hive_ops import _sanitize_hive
from src.reader import read_ticket
from tests.helpers import fail_nth_move, tree_snapshot, write_ticket_file

# Tickets of the fixture tree built by _build_fixture_tree: b.75s with a t1 child and t2 grandchild, and
# b.eiv whose child's ID does not match its parent's
FIXTURE_IDS = ["b.75s", "b.eiv", "t1.19d.6c", "t1.75s.65", "t2.75s.65.ab"]


def _age(directory: Path) -> None:
    """Make directory older than the 10 minutes empty-dir cleanup waits."""
    os.utime(directory, (time.time() - 1200,) * 2)


def _build_fixture_tree(owner_dir: Path) -> Path:
    """Write a test fixture tree, without `.hive/`, in owner_dir/prefix-tree/tickets/testplans.

    Returns the foreign subtree's root, owner_dir/prefix-tree. Besides the tickets of FIXTURE_IDS (b.75s
    without a children list, so a hive would get an add_child fix), it holds b.ue3 (an old ticket-ID dir with only
    a notes file) and an old empty ticket-ID dir b.emp, both of which cleanup would act on in a hive.
    """
    subtree = owner_dir / "prefix-tree"
    root = subtree / "tickets" / "testplans"
    write_ticket_file(root, "b.75s")
    write_ticket_file(root / "b.75s", "t1.75s.65", type="t1", parent="b.75s", children=["t2.75s.65.ab"])
    write_ticket_file(root / "b.75s" / "t1.75s.65", "t2.75s.65.ab", type="t2", parent="t1.75s.65")
    write_ticket_file(root, "b.eiv", children=["t1.19d.6c"])
    write_ticket_file(root / "b.eiv", "t1.19d.6c", type="t1", parent="b.eiv")
    (root / "b.ue3").mkdir()
    (root / "b.ue3" / "notes.txt").write_text("not a ticket")
    _age(root / "b.ue3")
    (root / "b.emp").mkdir()
    _age(root / "b.emp")
    return subtree


@pytest.fixture
def hive(make_hive):
    """Hive `test_hive` (tiers t1, t2) at tmp_path/hive, registered; returns its path."""
    return make_hive()


@pytest.fixture
def hive_with_fixture(hive):
    """The hive holds bee b.ai5, whose folder holds the fixture tree; returns (hive, fixture tree root)."""
    write_ticket_file(hive, "b.ai5")
    return hive, _build_fixture_tree(hive / "b.ai5")


def _lint(hive: Path, auto_fix: bool = True, detect_only: bool = False):
    return Linter(str(hive), hive_name="test_hive", auto_fix=auto_fix).run(detect_only=detect_only)


class TestForeignSubtreeLeftAlone:
    """The fixture tree is reported once and left exactly as it is (b.94t)."""

    async def test_sanitize_hive_leaves_foreign_subtree_untouched(self, hive_with_fixture):
        """No move, fix or error for the fixture's tickets; one warning for the subtree; the hive is not corrupt."""
        hive, root = hive_with_fixture
        before = tree_snapshot(hive)

        result = await _sanitize_hive("test_hive")

        assert tree_snapshot(hive) == before
        assert result["fixes_applied"] == []
        assert result["is_corrupt"] is False
        assert [(e["ticket_id"], e["error_type"], e["severity"]) for e in result["errors_remaining"]] == [
            ("b.ai5", "foreign_ticket_subtree", "warning")
        ]
        message = result["errors_remaining"][0]["message"]
        assert f"'{root}'" in message
        assert f"holds {len(FIXTURE_IDS)} ticket file(s)" in message
        assert all(ticket_id in message for ticket_id in FIXTURE_IDS)

    @pytest.mark.parametrize("auto_fix,detect_only", [(False, True), (True, True), (False, False)])
    def test_linter_reports_one_warning_and_validates_no_fixture_ticket(self, hive_with_fixture, auto_fix, detect_only):
        """Detect-only, auto-fix with detect_only and report-only runs alike: one warning, no other error."""
        hive, root = hive_with_fixture
        before = tree_snapshot(hive)

        report = _lint(hive, auto_fix=auto_fix, detect_only=detect_only)

        assert [(e.ticket_id, e.error_type, e.severity) for e in report.errors] == [
            ("b.ai5", "foreign_ticket_subtree", "warning")
        ]
        assert report.fixes == []
        assert not report.is_corrupt()
        assert tree_snapshot(hive) == before

    def test_message_lists_five_tickets_then_counts_the_rest(self, hive_with_fixture):
        """A subtree with more than five tickets shows the first five and how many more."""
        hive, root = hive_with_fixture
        for suffix in ("aaa", "bbb", "ccc"):
            write_ticket_file(root / "tickets", f"b.{suffix}")

        report = _lint(hive, auto_fix=False, detect_only=True)

        (warning,) = report.errors
        assert f"holds {len(FIXTURE_IDS) + 3} ticket file(s)" in warning.message
        assert "and 3 more)" in warning.message

    def test_scanner_yields_no_fixture_ticket_and_records_the_subtree(self, hive_with_fixture):
        """scan_all and scan_all_with_paths yield only the hive's tickets; foreign_subtrees names the rest."""
        hive, root = hive_with_fixture
        scanner = TicketScanner(str(hive), "test_hive")

        assert [t.id for t in scanner.scan_all()] == ["b.ai5"]
        assert [(t.id, p) for t, p in scanner.scan_all_with_paths()] == [("b.ai5", hive / "b.ai5" / "b.ai5.md")]
        assert list(scanner.foreign_subtrees) == [root]
        subtree = scanner.foreign_subtrees[root]
        assert subtree.owner_id == "b.ai5"
        assert sorted(subtree.ticket_ids) == FIXTURE_IDS

    def test_two_foreign_subtrees_get_two_warnings(self, hive_with_fixture):
        """Each foreign subtree root is reported once, under its own owner."""
        hive, _root = hive_with_fixture
        write_ticket_file(hive, "b.oth")
        write_ticket_file(hive / "b.oth" / "fixtures", "b.fff")

        report = _lint(hive, auto_fix=False, detect_only=True)

        assert sorted((e.ticket_id, e.error_type) for e in report.errors) == [
            ("b.ai5", "foreign_ticket_subtree"),
            ("b.oth", "foreign_ticket_subtree"),
        ]


class TestEmptyDirCleanupSkipsForeignSubtree:
    """An empty ticket-ID dir inside the foreign subtree is neither removed nor reported."""

    @pytest.mark.parametrize("auto_fix", [True, False])
    def test_foreign_dirs_kept_and_own_empty_dir_handled(self, hive_with_fixture, auto_fix):
        """Own old b.hhh is removed (auto-fix) or reported; the fixture's old b.emp and b.ue3 are neither."""
        hive, root = hive_with_fixture
        (hive / "b.hhh").mkdir()
        _age(hive / "b.hhh")
        before = tree_snapshot(root)

        report = _lint(hive, auto_fix=auto_fix)

        assert tree_snapshot(root) == before
        assert (root / "tickets" / "testplans" / "b.emp").is_dir()
        assert (root / "tickets" / "testplans" / "b.ue3" / "notes.txt").is_file()
        if auto_fix:
            assert [(f.ticket_id, f.fix_type) for f in report.fixes] == [("b.hhh", "remove_empty_dir")]
            assert not (hive / "b.hhh").exists()
        else:
            assert [e.ticket_id for e in report.get_errors(error_type="empty_ticket_dir")] == ["b.hhh"]
            assert (hive / "b.hhh").is_dir()


# (tickets to write as (subdir, id, fields), ids that must be moved, their directory below the hive afterwards)
STILL_MOVED_CASES = [
    pytest.param([("wrong", "b.xyz", {})], {"b.xyz": "b.xyz"}, id="bee_under_plain_dir"),
    pytest.param(
        [
            ("", "b.par", {"children": ["t1.par.aa"]}),
            ("b.par/misc", "t1.par.aa", {"type": "t1", "parent": "b.par"}),
        ],
        {"t1.par.aa": "b.par/t1.par.aa"},
        id="child_in_plain_dir_of_its_parent",
    ),
    pytest.param(
        [
            ("", "b.par", {"children": ["t1.par.aa"]}),
            ("b.par", "t1.par.aa", {"type": "t1", "parent": "b.par", "children": ["t2.par.aa.bb"]}),
            ("b.par/misc", "t2.par.aa.bb", {"type": "t2", "parent": "t1.par.aa"}),
        ],
        {"t2.par.aa.bb": "b.par/t1.par.aa/t2.par.aa.bb"},
        id="grandchild_in_plain_dir_of_its_grandparent",
    ),
]


class TestMisplacedTicketsStillMoved:
    """What is not under a foreign subtree is still the linter's to move, next to one and with ID copies in it."""

    @pytest.mark.parametrize("tickets,moved", STILL_MOVED_CASES)
    def test_misplaced_hive_tickets_moved_and_fixture_untouched(self, hive_with_fixture, tickets, moved):
        """Misplaced tickets land in their directory; the fixture tree is byte-identical."""
        hive, root = hive_with_fixture
        for subdir, ticket_id, fields in tickets:
            write_ticket_file(hive / subdir, ticket_id, **fields)
        before = tree_snapshot(root)

        report = _lint(hive)

        assert {f.ticket_id for f in report.fixes if f.fix_type == "move_directory"} == set(moved)
        for ticket_id, directory in moved.items():
            assert (hive / directory / f"{ticket_id}.md").is_file()
        assert [e.error_type for e in report.errors] == ["foreign_ticket_subtree"]
        assert tree_snapshot(root) == before

    def test_hive_ticket_with_an_id_inside_the_subtree_acts_on_the_hive_copy_only(self, hive_with_fixture):
        """Misplaced hive tickets sharing IDs with fixture tickets are moved without touching the fixture copies."""
        hive, root = hive_with_fixture
        write_ticket_file(hive / "wrong", "b.75s", title="Hive bee", children=["t1.75s.65"])
        write_ticket_file(hive / "misc", "t1.75s.65", title="Hive child", type="t1", parent="b.75s")
        before = tree_snapshot(root)

        report = _lint(hive)

        assert {f.ticket_id for f in report.fixes if f.fix_type == "move_directory"} == {"b.75s", "t1.75s.65"}
        assert report.get_errors(error_type="duplicate_id") == []
        assert [e.error_type for e in report.errors] == ["foreign_ticket_subtree"]
        bee, child = hive / "b.75s" / "b.75s.md", hive / "b.75s" / "t1.75s.65" / "t1.75s.65.md"
        assert (read_ticket("b.75s", file_path=bee).title, read_ticket("t1.75s.65", file_path=child).title) == (
            "Hive bee",
            "Hive child",
        )
        assert tree_snapshot(root) == before

    def test_foreign_subtree_moves_with_its_owner_and_stays_unswept(self, hive):
        """A misplaced owner is moved to the hive root with its folder; the cleanup that follows keeps b.emp."""
        write_ticket_file(hive / "wrong", "b.ai5")
        moved_root = hive / "b.ai5" / "prefix-tree"
        before = tree_snapshot(_build_fixture_tree(hive / "wrong" / "b.ai5"))

        report = _lint(hive)

        assert [(f.ticket_id, f.fix_type) for f in report.fixes] == [("b.ai5", "move_directory")]
        assert (hive / "b.ai5" / "b.ai5.md").is_file()
        assert tree_snapshot(moved_root) == before
        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.ai5", "foreign_ticket_subtree")]
        assert f"'{moved_root}'" in report.errors[0].message
        assert not (hive / "wrong" / "b.ai5" / "prefix-tree").exists()


class TestParentLookupSkipsForeignSubtree:
    """A ticket of the subtree is never taken for a hive ticket's parent or file (b.94t review)."""

    def test_child_goes_to_the_hive_parent_not_the_subtrees_copy_of_it(self, hive_with_fixture):
        """The fixture holds a b.eiv too; the hive's t1.eiv.aa is moved to the hive's b.eiv, the fixture is unchanged."""
        hive, root = hive_with_fixture
        write_ticket_file(hive, "b.eiv", children=["t1.eiv.aa"])
        write_ticket_file(hive / "misc", "t1.eiv.aa", type="t1", parent="b.eiv")
        before = tree_snapshot(root)

        report = _lint(hive)

        assert [(f.ticket_id, f.fix_type) for f in report.fixes] == [("t1.eiv.aa", "move_directory")]
        assert (hive / "b.eiv" / "t1.eiv.aa" / "t1.eiv.aa.md").is_file()
        assert not (hive / "misc" / "t1.eiv.aa").exists()
        assert tree_snapshot(root) == before

    def test_same_id_with_another_parent_in_the_subtree_does_not_make_the_hive_dir_foreign(self, hive):
        """A fixture's t1.par.aa under b.qqq does not make the hive's misplaced t1.par.aa a foreign copy."""
        write_ticket_file(hive, "b.par", children=["t1.par.aa"])
        write_ticket_file(hive / "b.par" / "misc", "t1.par.aa", type="t1", parent="b.par")
        write_ticket_file(hive, "b.zzz")
        fixture = hive / "b.zzz" / "fixture"
        write_ticket_file(fixture, "b.qqq", children=["t1.par.aa"])
        write_ticket_file(fixture / "b.qqq", "t1.par.aa", type="t1", parent="b.qqq")
        before = tree_snapshot(fixture)

        report = _lint(hive)

        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.zzz", "foreign_ticket_subtree")]
        assert f"'{fixture}'" in report.errors[0].message
        assert [(f.ticket_id, f.fix_type) for f in report.fixes] == [("t1.par.aa", "move_directory")]
        assert (hive / "b.par" / "t1.par.aa" / "t1.par.aa.md").is_file()
        assert tree_snapshot(fixture) == before

    @pytest.mark.parametrize(
        "ticket_id,ticket_type,foreign_root",
        [("t1.aaa.bc", "t1", None), ("b.yyy", "bee", "b.aaa/misc")],
        ids=["related_by_id", "unrelated"],
    )
    def test_non_string_parent_is_no_ancestor_and_stops_nothing_in_the_scan(
        self, hive, ticket_id, ticket_type, foreign_root
    ):
        """A list in parent (a field-type error for the linter to report) raises nothing in the foreign subtree search.

        The ID of t1.aaa.bc vouches for it by itself; b.yyy has no parent that could.
        """
        write_ticket_file(hive, "b.aaa", children=["t1.aaa.bc"])
        write_ticket_file(hive / "b.aaa" / "misc", ticket_id, type=ticket_type, parent=["b.aaa"])
        scanner = TicketScanner(str(hive), "test_hive")

        scanned = sorted(ticket.id for ticket in scanner.scan_all())

        assert scanned == (["b.aaa", ticket_id] if foreign_root is None else ["b.aaa"])
        assert list(scanner.foreign_subtrees) == ([] if foreign_root is None else [hive / foreign_root])

    @pytest.mark.parametrize(
        "children_yaml",
        ["5", '"t1.xyz.aa"', "{t1.xyz.aa: 1}"],
        ids=["int", "string_containing_the_id", "mapping"],
    )
    def test_children_that_is_not_a_list_claims_nothing_and_stops_nothing_in_the_scan(self, hive, children_yaml):
        """A bad children value (a field-type error for the linter to report) raises nothing and claims no child.

        A string holding the ID must not count as a listing by substring, so b.abc/notes stays foreign.
        """
        write_ticket_file(hive, "b.abc")
        write_ticket_file(hive, "b.xyz", raw_fields={"children": children_yaml})
        write_ticket_file(hive / "b.abc" / "notes", "t1.xyz.aa", type="t1", parent="b.xyz")
        scanner = TicketScanner(str(hive), "test_hive")

        scanned = sorted(ticket.id for ticket in scanner.scan_all())

        assert scanned == ["b.abc", "b.xyz"]
        assert list(scanner.foreign_subtrees) == [hive / "b.abc" / "notes"]

    def test_shallowest_file_of_a_duplicate_id_gives_the_parent(self, hive):
        """b.zzz is at b.par/b.zzz and again, under another parent, in b.ooo's fixture: the shallow one decides.

        b.par/misc/b.yyy has b.zzz as parent, and so is related to b.par through the settled b.zzz. If the deeper
        copy (parent b.qqq) won, b.par/misc would be foreign too.
        """
        write_ticket_file(hive, "b.par")
        write_ticket_file(hive, "b.zzz", parent="b.par")
        write_ticket_file(hive / "b.par" / "misc", "b.yyy", parent="b.zzz")
        write_ticket_file(hive, "b.ooo")
        write_ticket_file(hive / "b.ooo" / "fixture", "b.zzz", parent="b.qqq")
        scanner = TicketScanner(str(hive), "test_hive")

        scanned = [(ticket.id, path.relative_to(hive).as_posix()) for ticket, path in scanner.scan_all_with_paths()]

        assert ("b.yyy", "b.par/misc/b.yyy/b.yyy.md") in scanned
        assert ("b.zzz", "b.ooo/fixture/b.zzz/b.zzz.md") not in scanned
        assert list(scanner.foreign_subtrees) == [hive / "b.ooo" / "fixture"]


class TestForeignRootInsideMisplacedTicket:
    """What a move of the folder holding a foreign subtree does to it, and to the warning about it (b.94t review)."""

    def test_misplaced_bee_with_a_fixture_is_moved_and_the_fixture_goes_with_it(self, hive):
        """b.abc misplaced in its own folder holds a fixture of b.zzz: b.abc lands at its place, the fixture intact."""
        bee_dir = hive / "b.abc" / "misc" / "b.abc"
        write_ticket_file(bee_dir.parent, "b.abc")
        write_ticket_file(bee_dir / "fixture", "b.zzz")
        (bee_dir / "fixture" / "notes.txt").write_text("fixture notes")
        before = tree_snapshot(bee_dir / "fixture")
        new_root = hive / "b.abc" / "fixture"

        report = _lint(hive)

        assert [(f.ticket_id, f.fix_type) for f in report.fixes] == [("b.abc", "move_directory")]
        assert (hive / "b.abc" / "b.abc.md").is_file()
        assert tree_snapshot(new_root) == before
        assert not (bee_dir / "fixture").exists()
        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.abc", "foreign_ticket_subtree")]
        assert f"'{new_root}'" in report.errors[0].message

    def test_fixture_copying_the_owners_own_tickets_is_left_alone(self, hive):
        """Copies of b.ai5 and its child inside b.ai5's folder: no fix, no duplicate_id, one warning."""
        write_ticket_file(hive, "b.ai5", children=["t1.ai5.xy"])
        write_ticket_file(hive / "b.ai5", "t1.ai5.xy", type="t1", parent="b.ai5")
        copy = hive / "b.ai5" / "fixture" / "tickets" / "b.ai5"
        write_ticket_file(copy.parent, "b.ai5")
        write_ticket_file(copy, "t1.ai5.xy", type="t1", parent="b.ai5")
        before = tree_snapshot(hive)

        report = _lint(hive)

        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.ai5", "foreign_ticket_subtree")]
        assert report.fixes == []
        assert tree_snapshot(hive) == before

    def test_non_ticket_stem_file_makes_no_foreign_subtree(self, hive):
        """b.abc/design/design.md is a design note, not a ticket: no warning, and the file is left as it is."""
        write_ticket_file(hive, "b.abc")
        note = hive / "b.abc" / "design" / "design.md"
        note.parent.mkdir()
        note.write_text("# Design notes\n")

        report = _lint(hive)

        assert report.get_errors(error_type="foreign_ticket_subtree") == []
        assert note.read_text() == "# Design notes\n"

    @pytest.mark.parametrize("failing_call", [1, 2, 3, 4])
    def test_failed_move_keeps_the_fixtures_empty_ticket_dir(self, hive, monkeypatch, failing_call):
        """A move failing partway (to the temp dir, or one of the three entries) leaves b.emp in the fixture alone.

        Entries move in sorted order: 1 is the move to the temp dir, 2 b.abc.md, 3 fixture, 4 t1.abc.aa.
        """
        bee_dir = hive / "b.abc" / "misc" / "deeper" / "b.abc"
        write_ticket_file(bee_dir.parent, "b.abc", children=["t1.abc.aa"])
        write_ticket_file(bee_dir, "t1.abc.aa", type="t1", parent="b.abc")
        write_ticket_file(bee_dir / "fixture", "b.zzz")
        (bee_dir / "fixture" / "b.emp").mkdir()
        _age(bee_dir / "fixture" / "b.emp")
        fixture_bee = (bee_dir / "fixture" / "b.zzz" / "b.zzz.md").read_bytes()
        fail_nth_move(monkeypatch, failing_call)

        report = _lint(hive)

        assert sorted((e.ticket_id, e.error_type) for e in report.errors) == [
            ("b.abc", "directory_enforcement_failed"),
            ("b.abc", "foreign_ticket_subtree"),
        ]
        (empty_dir,) = hive.rglob("b.emp")
        assert empty_dir.is_dir()
        (fixture_file,) = hive.rglob("b.zzz.md")
        assert fixture_file.read_bytes() == fixture_bee
        assert empty_dir.parent == fixture_file.parent.parent
        warning = report.get_errors(error_type="foreign_ticket_subtree")[0]
        (named_root,) = re.findall(r"Directory '([^']+)'", warning.message)
        assert Path(named_root) == empty_dir.parent


class TestDanglingReferenceToForeignSubtree:
    """A reference to a ticket found only in a foreign subtree is reported, never cleared (b.94t review)."""

    @pytest.fixture
    def auto_fix_dangling(self, mock_global_bees_dir):
        """Turn auto_fix_dangling_refs on in the global config."""
        config_path = mock_global_bees_dir / "config.json"
        config_path.write_text(json.dumps({**json.loads(config_path.read_text()), "auto_fix_dangling_refs": True}))

    @pytest.fixture
    def hive_with_stray_bee(self, hive, auto_fix_dangling):
        """b.bbb is hand-placed at b.aaa/archive/b.bbb; b.ccc, b.ddd and t1.eee.aa refer to it. Returns (hive, root)."""
        write_ticket_file(hive, "b.aaa")
        write_ticket_file(hive / "b.aaa" / "archive", "b.bbb")
        write_ticket_file(hive, "b.ccc", up_dependencies=["b.bbb", "b.nnn"])
        write_ticket_file(hive, "b.ddd", down_dependencies=["b.bbb"])
        write_ticket_file(hive, "t1.eee.aa", type="t1", parent="b.bbb")
        return hive, hive / "b.aaa" / "archive"

    async def test_references_stay_and_errors_name_the_subtree(self, hive_with_stray_bee):
        """parent, up and down references to b.bbb give errors naming the subtree and are not removed."""
        hive, root = hive_with_stray_bee
        before = tree_snapshot(root)

        result = await _sanitize_hive("test_hive")

        errors = {
            (e["ticket_id"], e["error_type"]): e["message"]
            for e in result["errors_remaining"]
            if e["error_type"] in ("dangling_parent", "dangling_dependency")
        }
        assert set(errors) == {
            ("t1.eee.aa", "dangling_parent"),
            ("b.ccc", "dangling_dependency"),
            ("b.ddd", "dangling_dependency"),
        }
        assert all(f"found only in foreign subtree '{root}'" in message for message in errors.values())
        fix_types = {(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"]}
        assert ("t1.eee.aa", "clear_dangling_parent") not in fix_types
        assert ("b.ddd", "remove_dangling_dependency") not in fix_types
        assert read_ticket("t1.eee.aa", file_path=hive / "t1.eee.aa" / "t1.eee.aa.md").parent == "b.bbb"
        assert read_ticket("b.ddd", file_path=hive / "b.ddd" / "b.ddd.md").down_dependencies == ["b.bbb"]
        assert tree_snapshot(root) == before

    async def test_a_missing_ticket_is_still_cleared_next_to_it(self, hive_with_stray_bee):
        """With the same setting, the reference to b.nnn (found nowhere) is removed and b.bbb stays in up_dependencies."""
        hive, _root = hive_with_stray_bee

        result = await _sanitize_hive("test_hive")

        assert [(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"] if "dangling" in f["fix_type"]] == [
            ("b.ccc", "remove_dangling_dependency")
        ]
        assert read_ticket("b.ccc", file_path=hive / "b.ccc" / "b.ccc.md").up_dependencies == ["b.bbb"]


class TestForeignSubtreeOfAnotherHiveInScope:
    """A reference in one hive to a ticket found only in another hive's foreign subtree is kept (b.94t)."""

    async def test_cross_hive_reference_kept_with_auto_fix_dangling_refs(self, isolated_bees_env):
        """Sanitizing hive_a keeps b.qqq's up_dependency on b.xyz, hand-placed in hive_b, and reports it once."""
        hive_a = isolated_bees_env.create_hive("hive_a")
        hive_b = isolated_bees_env.create_hive("hive_b")
        isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})
        config_path = isolated_bees_env.global_bees_dir / "config.json"
        config_path.write_text(json.dumps({**json.loads(config_path.read_text()), "auto_fix_dangling_refs": True}))
        write_ticket_file(hive_b, "b.abc")
        write_ticket_file(hive_b / "b.abc" / "notes", "b.xyz")
        write_ticket_file(hive_a, "b.qqq", up_dependencies=["b.xyz"])
        before = tree_snapshot(hive_a)

        result = await _sanitize_hive("hive_a")

        assert tree_snapshot(hive_a) == before
        assert read_ticket("b.qqq", file_path=hive_a / "b.qqq" / "b.qqq.md").up_dependencies == ["b.xyz"]
        assert result["fixes_applied"] == []
        assert [(e["ticket_id"], e["error_type"]) for e in result["errors_remaining"]] == [
            ("b.qqq", "dangling_dependency")
        ]
        assert f"found only in foreign subtree '{hive_b / 'b.abc' / 'notes'}'" in result["errors_remaining"][0]["message"]


class TestMixedDirectoryWithSettledDuplicate:
    """A directory holding a copy of a settled ticket is a fixture, though another ticket in it looks related (b.94t)."""

    async def test_mixed_fixture_is_left_byte_identical_with_one_warning(self, hive):
        """b.abc/fixture holds a copy of t1.abc.de and a fixture-only t1.abc.zz: no duplicate_id, move or fix."""
        write_ticket_file(hive, "b.abc", children=["t1.abc.de"])
        write_ticket_file(hive / "b.abc", "t1.abc.de", type="t1", parent="b.abc")
        write_ticket_file(hive / "b.abc" / "fixture", "t1.abc.de", type="t1", parent="b.abc", title="Copy")
        write_ticket_file(hive / "b.abc" / "fixture", "t1.abc.zz", type="t1", parent="b.abc")
        before = tree_snapshot(hive)

        result = await _sanitize_hive("test_hive")

        assert tree_snapshot(hive) == before
        assert result["fixes_applied"] == []
        assert [(e["ticket_id"], e["error_type"], e["severity"]) for e in result["errors_remaining"]] == [
            ("b.abc", "foreign_ticket_subtree", "warning")
        ]


class TestTicketClaimedByItsSettledParent:
    """A top ticket that its own settled parent lists as a child is a hand-moved real ticket, not foreign (b.94t)."""

    @staticmethod
    def _layout(hive: Path, parent_children: list[str]) -> None:
        write_ticket_file(hive, "b.abc")
        write_ticket_file(hive, "b.xyz", children=parent_children)
        write_ticket_file(hive / "b.abc" / "notes", "t1.xyz.aa", type="t1", parent="b.xyz")

    async def test_listed_child_is_moved_home(self, hive):
        """t1.xyz.aa under b.abc/notes goes to b.xyz/t1.xyz.aa; no foreign warning."""
        self._layout(hive, ["t1.xyz.aa"])

        result = await _sanitize_hive("test_hive")

        assert (hive / "b.xyz" / "t1.xyz.aa" / "t1.xyz.aa.md").is_file()
        assert not (hive / "b.abc" / "notes" / "t1.xyz.aa").exists()
        assert [(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"]] == [
            ("t1.xyz.aa", "move_directory")
        ]
        assert [e for e in result["errors_remaining"] if e["error_type"] == "foreign_ticket_subtree"] == []

    async def test_unlisted_child_stays_put_with_a_warning(self, hive):
        """With children: [] on b.xyz nothing claims t1.xyz.aa, so b.abc/notes is foreign and untouched."""
        self._layout(hive, [])
        before = tree_snapshot(hive)

        result = await _sanitize_hive("test_hive")

        assert tree_snapshot(hive) == before
        assert [(e["ticket_id"], e["error_type"]) for e in result["errors_remaining"]] == [
            ("b.abc", "foreign_ticket_subtree")
        ]
        assert "not claimed by 'b.abc' or its lineage" in result["errors_remaining"][0]["message"]
