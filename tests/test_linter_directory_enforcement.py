"""
Unit tests for linter directory structure enforcement.

Tests the enforce_directory_structure() method which ensures tickets
are located in the correct directories based on their parent relationships.
Per PRD: Frontmatter is source of truth, filesystem structure is derived.
"""

import errno
import os
import re
import shutil
from pathlib import Path

import pytest

from src.linter import Linter
from src.linter_report import LinterReport
from src.mcp_hive_ops import _sanitize_hive
from src.reader import read_ticket
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import TICKET_ID_LINTER_CHILD1, TICKET_ID_LINTER_CHILD_SUBTASK


def _tree(root: Path) -> dict[str, bytes | None]:
    """Every file (its bytes) and directory (None) below root by relative path; hidden dirs and symlinks not entered.

    The random part of a temporary directory's name (`<id>.moving-<random>`) is shown as `*`.
    """
    tree = {}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        rel = Path(dirpath).relative_to(root)
        tree.update({(rel / d).as_posix(): None for d in dirs})
        tree.update({(rel / f).as_posix(): (Path(dirpath) / f).read_bytes() for f in files})
    return {re.sub(r"\.moving-[^/]+", ".moving-*", path): data for path, data in tree.items()}


def _files(root: Path) -> dict[str, bytes]:
    """The files of _tree(root), without its directories."""
    return {path: data for path, data in _tree(root).items() if data is not None}


def _entry_state(path: Path) -> tuple:
    """What the entry at path is: a symlink and its target, a directory and its tree, or a file and its bytes."""
    if path.is_symlink():
        return ("symlink", os.readlink(path))
    if path.is_dir():
        return ("dir", _tree(path))
    return ("file", path.read_bytes())


def _moved(before: dict[str, bytes | None], old_dir: str, new_dir: str) -> dict[str, bytes]:
    """The files of a tree snapshot with everything under old_dir placed under new_dir instead."""
    return {
        new_dir + path[len(old_dir) :] if path.startswith(old_dir + "/") else path: data
        for path, data in before.items()
        if data is not None
    }


def _with_dirs(files: dict[str, bytes]) -> dict[str, bytes | None]:
    """The tree holding exactly these files and their parent directories, no other directory."""
    dirs = {parent.as_posix(): None for path in files for parent in Path(path).parents if parent != Path(".")}
    return {**dirs, **files}


def _build(hive: Path, tickets: list, other_files: dict[str, str]) -> None:
    """Write tickets given as (subdir, id, fields) and other files given as {path: text}, both relative to hive."""
    for subdir, ticket_id, fields in tickets:
        write_ticket_file(hive / subdir, ticket_id, **fields)
    for path, text in other_files.items():
        (hive / path).parent.mkdir(parents=True, exist_ok=True)
        (hive / path).write_text(text)


def _lint(hive: Path) -> LinterReport:
    """Run the auto-fixing linter on hive `test_hive` at hive."""
    return Linter(str(hive), hive_name="test_hive", auto_fix=True).run()


def _fail_move(monkeypatch, call: int) -> None:
    """Make shutil.move, as src.linter uses it, raise OSError on its call-th call only."""
    real_move = shutil.move
    calls = []

    def move(src, dst, *args, **kwargs):
        calls.append(src)
        if len(calls) == call:
            raise OSError(errno.EIO, "injected move failure", src)
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr("src.linter.shutil.move", move)


@pytest.fixture
def make_hive(tmp_path, monkeypatch, mock_global_bees_dir):
    """Factory: make_hive(dirname) registers tmp_path/dirname as hive `test_hive` (tiers t1, t2), returns its path."""
    monkeypatch.chdir(tmp_path)

    def make(dirname: str = "hive") -> Path:
        hive_path = tmp_path / dirname
        hive_path.mkdir()
        hives = {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}}
        tiers = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": hives, "child_tiers": tiers})
        return hive_path

    with repo_root_context(tmp_path):
        yield make


class TestEnforceDirectoryStructureBees:
    """Tests for bee directory enforcement (bees should be at hive root)."""

    def test_bee_at_hive_root_no_move(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Bee already at hive root should not be moved."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create bee at correct location (hive root)
        write_ticket_file(hive_path, "b.Amx", title="Test Bee", type="bee")

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should not report any moves
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) == 0

        # Bee should still be at hive root
        assert (hive_path / "b.Amx" / "b.Amx.md").exists()

    def test_bee_in_subdirectory_moved_to_hive_root(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Misplaced bee in subdirectory should be moved to hive root."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        (tmp_path / ".git").mkdir()  # Make it a repo
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create bee in wrong location (nested subdirectory)
        wrong_location = hive_path / "wrong" / "b.Amx"
        wrong_location.mkdir(parents=True)
        write_ticket_file(wrong_location, "b.Amx", title="Test Bee", type="bee")

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should report a directory move
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) == 1
        assert move_fixes[0].ticket_id == "b.Amx"
        assert "hive root" in move_fixes[0].description

        # Bee should now be at hive root
        assert (hive_path / "b.Amx" / "b.Amx.md").exists()
        assert not (wrong_location / "b.Amx.md").exists()

    def test_multiple_bees_at_various_depths_all_moved_to_root(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Multiple misplaced bees should all be moved to hive root."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create bees at various wrong locations
        wrong_loc_1 = hive_path / "subdir1" / "b.Amx"
        wrong_loc_2 = hive_path / "subdir2" / "deep" / "b.Bny"
        wrong_loc_3 = hive_path / "subdir3" / "very" / "deep" / "path" / "b.Czp"

        for loc in [wrong_loc_1, wrong_loc_2, wrong_loc_3]:
            loc.mkdir(parents=True)
            bee_id = loc.name
            write_ticket_file(loc, bee_id, title=f"Bee {bee_id}", type="bee")

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should report 3 directory moves
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) == 3

        # All bees should now be at hive root
        assert (hive_path / "b.Amx" / "b.Amx.md").exists()
        assert (hive_path / "b.Bny" / "b.Bny.md").exists()
        assert (hive_path / "b.Czp" / "b.Czp.md").exists()


class TestEnforceDirectoryStructureChildren:
    """Tests for child ticket directory enforcement (should be under parent)."""

    def test_child_under_parent_no_move(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Child ticket already under parent should not be moved."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create bee at hive root
        write_ticket_file(hive_path, "b.Amx", title="Parent Bee", type="bee", children=[TICKET_ID_LINTER_CHILD1])
        bee_dir = hive_path / "b.Amx"

        # Create child under parent (correct location)
        write_ticket_file(bee_dir, TICKET_ID_LINTER_CHILD1, title="Child Task", type="t1", parent="b.Amx")

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should not report any moves
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) == 0

        # Child should still be under parent
        assert (bee_dir / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md").exists()

    def test_child_not_under_parent_moved(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Child ticket not under parent should be moved to correct location."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create bee at hive root
        write_ticket_file(hive_path, "b.Amx", title="Parent Bee", type="bee", children=[TICKET_ID_LINTER_CHILD1])
        bee_dir = hive_path / "b.Amx"

        # Create child in wrong location (at hive root instead of under parent)
        write_ticket_file(hive_path, TICKET_ID_LINTER_CHILD1, title="Child Task", type="t1", parent="b.Amx")
        wrong_child_dir = hive_path / TICKET_ID_LINTER_CHILD1

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should report a directory move
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) == 1
        assert move_fixes[0].ticket_id == TICKET_ID_LINTER_CHILD1
        assert "parent" in move_fixes[0].description.lower()

        # Child should now be under parent
        assert (bee_dir / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md").exists()
        assert not (wrong_child_dir / f"{TICKET_ID_LINTER_CHILD1}.md").exists()

    def test_child_under_wrong_parent_moved_to_correct_parent(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Child under wrong parent should be moved to correct parent."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create two bees at hive root
        write_ticket_file(hive_path, "b.Amx", title="Parent Bee 1", type="bee", children=[TICKET_ID_LINTER_CHILD1])
        bee1_dir = hive_path / "b.Amx"

        write_ticket_file(hive_path, "b.Bny", title="Parent Bee 2", type="bee", children=[])
        bee2_dir = hive_path / "b.Bny"

        # Create child under wrong parent (bee2 instead of bee1)
        write_ticket_file(bee2_dir, TICKET_ID_LINTER_CHILD1, title="Child Task", type="t1", parent="b.Amx")
        _wrong_parent_child_dir = bee2_dir / TICKET_ID_LINTER_CHILD1

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should report a directory move
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) == 1
        assert move_fixes[0].ticket_id == TICKET_ID_LINTER_CHILD1

        # Child should now be under correct parent (bee1)
        assert (bee1_dir / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md").exists()
        assert not (bee2_dir / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md").exists()


class TestEnforceDirectoryStructurePreservesChildren:
    """Tests that moving directories preserves their child subdirectories."""

    def test_moving_parent_preserves_child_subdirectories(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Moving a misplaced parent should preserve all child subdirectories."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {
                    "t1": ["Task", "Tasks"],
                    "t2": ["Subtask", "Subtasks"],
                },
            },
        )

        # Create bee at hive root
        write_ticket_file(hive_path, "b.Amx", title="Parent Bee", type="bee", children=[TICKET_ID_LINTER_CHILD1])
        bee_dir = hive_path / "b.Amx"

        # Create child in wrong location with its own grandchild
        wrong_parent_dir = hive_path / "wrong"
        wrong_parent_dir.mkdir(parents=True)
        write_ticket_file(
            wrong_parent_dir,
            TICKET_ID_LINTER_CHILD1,
            title="Child Task",
            type="t1",
            parent="b.Amx",
            children=[TICKET_ID_LINTER_CHILD_SUBTASK],
        )
        wrong_child_dir = wrong_parent_dir / TICKET_ID_LINTER_CHILD1

        # Create grandchild under child
        write_ticket_file(wrong_child_dir, TICKET_ID_LINTER_CHILD_SUBTASK, title="Grandchild Subtask", type="t2", parent=TICKET_ID_LINTER_CHILD1)
        _grandchild_dir = wrong_child_dir / TICKET_ID_LINTER_CHILD_SUBTASK

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should move the child (and its grandchild subtree)
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) >= 1

        # Child should now be under parent
        assert (bee_dir / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md").exists()

        # Grandchild should still be under child (preserved during move)
        assert (bee_dir / TICKET_ID_LINTER_CHILD1 / TICKET_ID_LINTER_CHILD_SUBTASK / f"{TICKET_ID_LINTER_CHILD_SUBTASK}.md").exists()


class TestEnforceDirectoryStructureEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parent_not_found_skips_enforcement(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """If parent ticket doesn't exist, should skip enforcement for child."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {"test_hive": {"path": str(hive_path), "display_name": "Test Hive"}},
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create child without parent existing
        write_ticket_file(hive_path, TICKET_ID_LINTER_CHILD1, title="Orphan Task", type="t1", parent="b.MISSING")
        _child_dir = hive_path / TICKET_ID_LINTER_CHILD1

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should not crash, should skip enforcement
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory" and f.ticket_id == TICKET_ID_LINTER_CHILD1]
        assert len(move_fixes) == 0

    def test_no_hives_configured_skips_enforcement(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """If no hives are configured, should skip enforcement gracefully."""
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path
        hive_path = tmp_path / "hive"
        hive_path.mkdir()

        # Set up config with no hives
        write_scoped_config(mock_global_bees_dir, repo_root, {"hives": {}, "child_tiers": {}})

        write_ticket_file(hive_path, "b.Amx", title="Test Bee", type="bee")

        linter = Linter(str(hive_path), hive_name="test_hive")
        with repo_root_context(repo_root):
            report = linter.run()

        # Should not crash, should skip enforcement
        assert report is not None


class TestEnforceDirectoryStructureNestedHive:
    """Regression tests for nested hive sanitize bug (b.9ia).

    Bug: enforce_directory_structure() searched ALL hives to find tickets,
    causing nested hive bees (e.g. Plans at ideas/Plans/) to be found by
    the parent hive linter (Ideas at ideas/) and moved to the parent root.

    Fix: linter now uses self.hive_name and self.tickets_dir directly,
    so it only sees tickets in its own hive.
    """

    def test_nested_hive_bees_not_moved_to_parent_root(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Bees in a nested child hive must not be moved to the parent hive root.

        Regression test for b.9ia: when enforce_directory_structure() ran on
        the Plans hive linter, it previously searched all hives and found the
        Plans bee under ideas/Plans/b.xxx/. Because that path is under the
        Ideas hive root (ideas/), the old code treated it as misplaced and
        moved it to ideas/b.xxx/. The fix scopes the search to self.tickets_dir,
        so the Plans linter only sees ideas/Plans/ and leaves the bee alone.
        """
        monkeypatch.chdir(tmp_path)
        repo_root = tmp_path

        # Set up nested hive structure:
        #   ideas/         <- Ideas hive root
        #   ideas/Plans/   <- Plans hive root (nested inside Ideas)
        ideas_path = tmp_path / "ideas"
        ideas_path.mkdir()
        plans_path = ideas_path / "Plans"
        plans_path.mkdir()

        # Register both hives in config
        write_scoped_config(
            mock_global_bees_dir,
            repo_root,
            {
                "hives": {
                    "ideas": {"path": str(ideas_path), "display_name": "Ideas"},
                    "plans": {"path": str(plans_path), "display_name": "Plans"},
                },
                "child_tiers": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create a bee in the Plans hive at the correct location: ideas/Plans/b.Amx/
        write_ticket_file(plans_path, "b.Amx", title="Plans Bee", type="bee")

        # Run enforce_directory_structure() on the Plans hive linter only
        linter = Linter(str(plans_path), hive_name="plans")
        with repo_root_context(repo_root):
            report = linter.run()

        # The bee must NOT have been moved — no move_directory fixes expected
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        assert len(move_fixes) == 0, (
            f"Nested hive bee was incorrectly moved: {[f.description for f in move_fixes]}"
        )

        # Bee must still be at ideas/Plans/b.Amx/b.Amx.md (its correct location)
        assert (plans_path / "b.Amx" / "b.Amx.md").exists(), (
            "Bee should remain at ideas/Plans/b.Amx/ but was moved or deleted"
        )

        # Bee must NOT have been moved up to the Ideas hive root
        assert not (ideas_path / "b.Amx" / "b.Amx.md").exists(), (
            "Bee was incorrectly moved to parent hive root ideas/b.Amx/"
        )


# (tickets as (subdir, id, fields), other files, moved ticket, its directory before and after the move)
INSIDE_OWN_DIR_CASES = [
    pytest.param(
        [("b.abc/misc", "b.abc", {})],
        {"b.abc/misc/note.txt": "unrelated"},
        "b.abc",
        "b.abc/misc/b.abc",
        "b.abc",
        id="bee_below_subdir_of_own_dir",
    ),
    pytest.param([("b.abc", "b.abc", {})], {}, "b.abc", "b.abc/b.abc", "b.abc", id="bee_directly_in_own_dir"),
    pytest.param(
        [
            ("b.abc/misc/deeper", "b.abc", {"children": ["t1.abc.aa"]}),
            ("b.abc/misc/deeper/b.abc", "t1.abc.aa", {"type": "t1", "parent": "b.abc"}),
        ],
        {},
        "b.abc",
        "b.abc/misc/deeper/b.abc",
        "b.abc",
        id="bee_with_child_emptying_dirs_on_the_way",
    ),
    pytest.param(
        [
            ("", "b.par", {"children": ["t1.par.aa"]}),
            ("b.par/t1.par.aa/misc", "t1.par.aa", {"type": "t1", "parent": "b.par"}),
        ],
        {"b.par/t1.par.aa/misc/note.txt": "unrelated"},
        "t1.par.aa",
        "b.par/t1.par.aa/misc/t1.par.aa",
        "b.par/t1.par.aa",
        id="child_below_subdir_of_own_dir",
    ),
]

# (hive dir name, tickets as (subdir, id, fields), other files, entry made a symlink to tmp_path/outside); b.abc refused
CONFLICT_CASES = [
    pytest.param(
        "hive",
        [("misplaced", "b.abc", {})],
        {"misplaced/b.abc/notes.txt": "mine", "b.abc/notes.txt": "theirs"},
        None,
        id="name_taken_in_target",
    ),
    pytest.param(
        "hive",
        [("b.abc", "b.abc", {})],
        {"b.abc/b.abc/notes.txt": "mine", "b.abc/notes.txt": "theirs"},
        None,
        id="name_taken_in_target_holding_ticket",
    ),
    pytest.param("hive", [("misplaced", "b.abc", {})], {"b.abc": "a file"}, None, id="target_is_file"),
    pytest.param("hive", [("misplaced", "b.abc", {})], {}, "b.abc", id="target_is_symlink"),
    # The hive root is the bee's directory, so the bee's expected directory lies inside it
    pytest.param("b.abc", [("..", "b.abc", {})], {}, None, id="target_inside_ticket_dir"),
    pytest.param(
        "b.abc", [("..", "b.abc", {})], {"b.abc/notes.txt": "theirs"}, None, id="existing_target_inside_ticket_dir"
    ),
]


# Tickets as (subdir, id, fields), each the parent of the one before it and inside its directory, so they are
# listed children first, as a top-down scan finds them; then each ticket's directory after one run
PARENT_INSIDE_CHILD_CASES = [
    pytest.param(
        [("", "t1.abc.aa", {"type": "t1", "parent": "b.abc"}), ("t1.abc.aa", "b.abc", {"children": ["t1.abc.aa"]})],
        {"t1.abc.aa": "b.abc/t1.abc.aa", "b.abc": "b.abc"},
        id="bee_inside_child_dir",
    ),
    pytest.param(
        [
            ("", "t2.abc.aa.bb", {"type": "t2", "parent": "t1.abc.aa"}),
            ("t2.abc.aa.bb", "t1.abc.aa", {"type": "t1", "parent": "b.abc", "children": ["t2.abc.aa.bb"]}),
            ("t2.abc.aa.bb/t1.abc.aa", "b.abc", {"children": ["t1.abc.aa"]}),
        ],
        {"t2.abc.aa.bb": "b.abc/t1.abc.aa/t2.abc.aa.bb", "t1.abc.aa": "b.abc/t1.abc.aa", "b.abc": "b.abc"},
        id="bee_inside_t1_inside_t2_dir",
    ),
]

# Where the bee's directory is, then where its notes.txt stays when the merge stops
TAKEN_NAME_CASES = [
    pytest.param("misplaced/b.abc", "misplaced/b.abc", id="merge"),
    pytest.param("b.abc/misc/b.abc", "b.abc.moving-*/b.abc", id="merge_from_temp_dir"),
]

# Ways to take the name of an entry in the target directory
TAKE_NAME = [
    pytest.param(lambda path: path.write_text("theirs"), id="file"),
    pytest.param(lambda path: (path.mkdir(), (path / "keep.txt").write_text("theirs")), id="dir"),
    pytest.param(lambda path: path.symlink_to(path.parent / "nowhere"), id="dangling_symlink"),
]

# A bee with a child and a file, misplaced inside its own expected directory
DEEP_BEE = "b.abc/misc/deeper/b.abc"
DEEP_BEE_TICKETS = [
    ("b.abc/misc/deeper", "b.abc", {"children": ["t1.abc.aa"]}),
    (DEEP_BEE, "t1.abc.aa", {"type": "t1", "parent": "b.abc"}),
]
DEEP_BEE_TICKET_FILES = ["b.abc.md", "t1.abc.aa/t1.abc.aa.md"]

# The shutil.move call that fails (1: DEEP_BEE to the temp dir, then from there 2: b.abc.md, 3: notes.txt), where
# the bee and its child are after that run, where notes.txt is after it, and where notes.txt is after a clean rerun
FAILED_MOVE_CASES = [
    pytest.param(1, DEEP_BEE, DEEP_BEE, "b.abc", id="move_to_temp_dir"),
    pytest.param(2, "b.abc.moving-*/b.abc", "b.abc.moving-*/b.abc", "b.abc", id="first_move_from_temp_dir"),
    pytest.param(3, "b.abc", "b.abc.moving-*/b.abc", "b.abc.moving-*/b.abc", id="later_move_from_temp_dir"),
]


class TestEnforceDirectoryStructureExistingTarget:
    """Regression tests for b.78s: a move into an existing expected directory never deletes anything.

    Bug: enforcement ran rmtree on an existing expected directory before moving the ticket in,
    deleting whatever it held, including the ticket itself when it was misplaced inside it.
    """

    @pytest.mark.parametrize("tickets,other_files,ticket_id,old_dir,new_dir", INSIDE_OWN_DIR_CASES)
    async def test_ticket_inside_own_expected_dir_moved_up(
        self, make_hive, tickets, other_files, ticket_id, old_dir, new_dir
    ):
        """Sanitize moves the ticket's files to its expected dir unchanged, keeps others, leaves no temp/emptied dir."""
        hive = make_hive()
        _build(hive, tickets, other_files)
        before = _tree(hive)

        result = await _sanitize_hive("test_hive")

        assert [(f["ticket_id"], f["fix_type"]) for f in result["fixes_applied"]] == [(ticket_id, "move_directory")]
        assert result["errors_remaining"] == []
        assert _tree(hive) == _with_dirs(_moved(before, old_dir, new_dir))

    @pytest.mark.parametrize("tickets,new_dirs", PARENT_INSIDE_CHILD_CASES)
    def test_parent_inside_child_dir_settled_in_one_run(self, make_hive, tickets, new_dirs):
        """Given children first, parents still move first: every ticket lands in place in one run, byte-identical."""
        hive = make_hive()
        _build(hive, tickets, {})
        old_files = {tid: Path(subdir, tid, f"{tid}.md").as_posix() for subdir, tid, _ in tickets}
        before = _tree(hive)
        children_first = [read_ticket(tid, file_path=hive / path) for tid, path in old_files.items()]
        report = LinterReport()

        Linter(str(hive), hive_name="test_hive", auto_fix=True).enforce_directory_structure(children_first, report)

        assert report.errors == []
        fixes = sorted((f.ticket_id, f.fix_type) for f in report.fixes)
        assert fixes == [(tid, "move_directory") for tid in sorted(new_dirs)]
        assert _tree(hive) == _with_dirs({f"{new_dirs[tid]}/{tid}.md": before[path] for tid, path in old_files.items()})

    def test_parent_cycle_ends_without_loss(self, make_hive):
        """Tickets whose parents form a cycle are still ordered and checked: the run ends, every ticket file kept."""
        hive = make_hive()
        tickets = [
            ("", "b.abc", {}),
            ("b.abc", "t1.abc.aa", {"type": "t1", "parent": "t1.abc.bb"}),
            ("b.abc", "t1.abc.bb", {"type": "t1", "parent": "t1.abc.aa"}),
        ]
        _build(hive, tickets, {})

        _lint(hive)

        assert sorted(Path(path).name for path in _files(hive)) == ["b.abc.md", "t1.abc.aa.md", "t1.abc.bb.md"]

    def test_existing_expected_dir_merged_into(self, make_hive):
        """A bee moved onto its existing dir joins the child and file already there; nothing is lost."""
        hive = make_hive()
        tickets = [
            ("misplaced", "b.abc", {"children": ["t1.abc.aa"]}),
            ("b.abc", "t1.abc.aa", {"type": "t1", "parent": "b.abc"}),
        ]
        _build(hive, tickets, {"b.abc/notes.txt": "unrelated"})
        before = _tree(hive)

        report = _lint(hive)

        assert report.errors == []
        assert ("b.abc", "move_directory") in [(f.ticket_id, f.fix_type) for f in report.fixes]
        assert _files(hive) == _moved(before, "misplaced/b.abc", "b.abc")
        assert not (hive / "misplaced" / "b.abc").exists()

    @pytest.mark.parametrize("hive_dir,tickets,other_files,symlink", CONFLICT_CASES)
    def test_conflicting_move_refused(self, make_hive, tmp_path, hive_dir, tickets, other_files, symlink):
        """A move that would overwrite an entry or nest the target in the ticket's dir is reported; no file changes."""
        hive = make_hive(hive_dir)
        _build(hive, tickets, other_files)
        if symlink:
            _build(tmp_path, [], {"outside/keep.txt": "theirs"})
            (hive / symlink).symlink_to(tmp_path / "outside", target_is_directory=True)
        before = _tree(tmp_path)

        report = _lint(hive)

        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.abc", "move_target_conflict")]
        assert report.fixes == []
        assert _tree(tmp_path) == before

    @pytest.mark.parametrize("take_name", TAKE_NAME)
    @pytest.mark.parametrize("bee_dir,notes_left_in", TAKEN_NAME_CASES)
    def test_name_taken_during_merge_kept(self, make_hive, monkeypatch, bee_dir, notes_left_in, take_name):
        """A name taken in the target after the conflict check stops the merge; it is not overwritten or nested into."""
        hive = make_hive()
        other_files = {f"{bee_dir}/notes.txt": "mine", "b.abc/other.txt": "theirs"}
        _build(hive, [(str(Path(bee_dir).parent), "b.abc", {})], other_files)
        taken = hive / "b.abc" / "notes.txt"
        taken_states = []
        real_check = Linter._find_move_conflict

        def check_then_take_name(current_dir: Path, expected_dir: Path) -> str | None:
            conflict = real_check(current_dir, expected_dir)
            take_name(taken)
            taken_states.append(_entry_state(taken))
            return conflict

        monkeypatch.setattr(Linter, "_find_move_conflict", staticmethod(check_then_take_name))

        report = _lint(hive)

        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.abc", "directory_enforcement_failed")]
        assert taken_states == [_entry_state(taken)]
        assert [path.read_text() for path in hive.glob(f"{notes_left_in}/notes.txt")] == ["mine"]

    @pytest.mark.parametrize("failing_call,tickets_dir,notes_dir,notes_dir_after_rerun", FAILED_MOVE_CASES)
    def test_failed_move_through_temp_dir_loses_nothing(
        self, make_hive, monkeypatch, failing_call, tickets_dir, notes_dir, notes_dir_after_rerun
    ):
        """A move via the temp dir failing partway is reported; only empty dirs go; no file is lost, nor on rerun."""
        hive = make_hive()
        _build(hive, DEEP_BEE_TICKETS, {f"{DEEP_BEE}/notes.txt": "mine"})
        before = _tree(hive)
        ticket_files = {name: before[f"{DEEP_BEE}/{name}"] for name in DEEP_BEE_TICKET_FILES}
        _fail_move(monkeypatch, failing_call)

        report = _lint(hive)

        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.abc", "directory_enforcement_failed")]
        after = {f"{tickets_dir}/{name}": data for name, data in ticket_files.items()}
        assert _tree(hive) == {"b.abc": None, **_with_dirs({**after, f"{notes_dir}/notes.txt": b"mine"})}

        rerun = _lint(hive)

        assert rerun.errors == []
        settled = {f"b.abc/{name}": data for name, data in ticket_files.items()}
        assert _files(hive) == {**settled, f"{notes_dir_after_rerun}/notes.txt": b"mine"}

    def test_temp_dir_cleanup_failure_keeps_move_error(self, make_hive, monkeypatch):
        """When removing the temp dir fails after a failed move, the move's own error is still the one reported."""
        hive = make_hive()
        _build(hive, DEEP_BEE_TICKETS, {})
        _fail_move(monkeypatch, 1)
        real_rmdir = Path.rmdir

        def rmdir(path: Path) -> None:
            if ".moving-" in path.name:
                raise PermissionError(errno.EACCES, "injected rmdir failure", str(path))
            real_rmdir(path)

        monkeypatch.setattr(Path, "rmdir", rmdir)

        report = _lint(hive)

        assert [(e.ticket_id, e.error_type) for e in report.errors] == [("b.abc", "directory_enforcement_failed")]
        assert "injected move failure" in report.errors[0].message
