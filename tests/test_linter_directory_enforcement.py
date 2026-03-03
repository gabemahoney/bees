"""
Unit tests for linter directory structure enforcement.

Tests the enforce_directory_structure() method which ensures tickets
are located in the correct directories based on their parent relationships.
Per PRD: Frontmatter is source of truth, filesystem structure is derived.
"""



from src.linter import Linter
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import TICKET_ID_LINTER_CHILD1, TICKET_ID_LINTER_CHILD_SUBTASK


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
