"""
Unit tests for the undertaker MCP tool — archives bee tickets to cemetery/.

PURPOSE:
Tests the _undertaker function which executes queries to find bees, then
moves their directory trees into the hive's cemetery/ directory with
GUID-based renaming.

SCOPE - Tests that belong here:
- Happy path: bee + children archived, guids collected, originals removed
- Non-bee filtering: t1/t2 tickets in results are skipped
- Parameter validation: both params error, neither params error
- Cemetery directory auto-creation and pre-existence

SCOPE - Tests that DON'T belong here:
- Query parsing -> test_query_parser.py
- Pipeline execution -> test_pipeline.py
- Selective traversal exclusion -> test_paths.py

RELATED FILES:
- test_pipeline.py: Query pipeline used by undertaker
- test_paths.py: find_ticket_file used in Phase 1
"""

from unittest.mock import MagicMock, patch


from src.config import BeesConfig, HiveConfig
from src.constants import ID_CHARSET
from src.mcp_undertaker import UndertakerScheduler, _undertaker


def _make_guid(short_id: str) -> str:
    """Build a deterministic 32-char GUID for testing."""
    filler = ID_CHARSET[0]  # "1"
    return (short_id + filler * 32)[:32]


class TestUndertaker:
    """Tests for _undertaker async function."""

    async def test_happy_path_archives_bee_and_children(self, isolated_bees_env):
        """Bee with 2 child tasks: all 3 archived, guids collected, originals removed."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        bee_guid = _make_guid("abc")
        t1a_guid = _make_guid("defga")
        t1b_guid = _make_guid("hijka")

        helper.create_ticket(hive_dir, "b.abc", "bee", "Parent Bee", guid=bee_guid)
        helper.create_ticket(hive_dir / "b.abc", "t1.def.ga", "t1", "Child A", parent="b.abc", guid=t1a_guid)
        helper.create_ticket(hive_dir / "b.abc", "t1.hij.ka", "t1", "Child B", parent="b.abc", guid=t1b_guid)

        result = await _undertaker(
            hive_name="test_hive",
            query_yaml="- ['type=bee']",
        )

        assert result["status"] == "success"
        assert result["archived_count"] >= 3
        assert sorted(result["archived_guids"]) == sorted([bee_guid, t1a_guid, t1b_guid])
        assert result["skipped"] == []

        # Original bee directory should be gone
        assert not (hive_dir / "b.abc").exists()

        # Cemetery should exist with renamed content
        cemetery = hive_dir / "cemetery"
        assert cemetery.exists()

        # Verify at least one GUID-renamed .md file exists in cemetery
        all_md = list(cemetery.rglob("*.md"))
        assert len(all_md) >= 3

    async def test_non_bee_in_query_results_skipped(self, isolated_bees_env):
        """Non-bee tickets in query results should be skipped, not archived."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        t1_guid = _make_guid("wxyza")
        helper.create_ticket(hive_dir, "t1.wxy.za", "t1", "Orphan Task", guid=t1_guid)

        result = await _undertaker(
            hive_name="test_hive",
            query_yaml="- ['type=t1']",
        )

        assert result["status"] == "success"
        assert result["archived_count"] == 0
        assert result["archived_guids"] == []
        assert "t1.wxy.za" in result["skipped"]

        # Ticket should still exist (not moved)
        assert (hive_dir / "t1.wxy.za" / "t1.wxy.za.md").exists()

    async def test_both_params_error(self, isolated_bees_env):
        """Providing both query_yaml and query_name returns error, nothing archived."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        helper.create_ticket(hive_dir, "b.nop", "bee", "Should Not Move", guid=_make_guid("nop"))

        result = await _undertaker(
            hive_name="test_hive",
            query_yaml="- ['type=bee']",
            query_name="some_query",
        )

        assert result["status"] == "error"
        assert "not both" in result["message"]

        # Ticket should still exist
        assert (hive_dir / "b.nop" / "b.nop.md").exists()

    async def test_neither_param_error(self, isolated_bees_env):
        """Providing neither query_yaml nor query_name returns error."""
        helper = isolated_bees_env
        helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        result = await _undertaker(hive_name="test_hive")

        assert result["status"] == "error"
        assert "Provide either" in result["message"]

    async def test_named_query_not_found_returns_distinct_error(self, isolated_bees_env):
        """query_name that resolves to not_found returns query_not_found error_type."""
        helper = isolated_bees_env
        helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        with patch(
            "src.mcp_undertaker.resolve_named_query",
            return_value={"status": "not_found"},
        ):
            result = await _undertaker(
                hive_name="test_hive",
                query_name="missing_query",
            )

        assert result["status"] == "error"
        assert result["error_type"] == "query_not_found"
        assert "missing_query" in result["message"]

    async def test_named_query_out_of_scope_returns_distinct_error(self, isolated_bees_env):
        """query_name that resolves to out_of_scope returns query_out_of_scope error_type."""
        helper = isolated_bees_env
        helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        with patch(
            "src.mcp_undertaker.resolve_named_query",
            return_value={"status": "out_of_scope"},
        ):
            result = await _undertaker(
                hive_name="test_hive",
                query_name="scoped_query",
            )

        assert result["status"] == "error"
        assert result["error_type"] == "query_out_of_scope"
        assert "scoped_query" in result["message"]

    async def test_cemetery_auto_creation(self, isolated_bees_env):
        """Cemetery directory should be created automatically when missing."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        bee_guid = _make_guid("xyz")
        helper.create_ticket(hive_dir, "b.xyz", "bee", "Auto Cemetery", guid=bee_guid)

        assert not (hive_dir / "cemetery").exists()

        result = await _undertaker(
            hive_name="test_hive",
            query_yaml="- ['type=bee']",
        )

        assert result["status"] == "success"
        assert result["archived_count"] >= 1
        assert (hive_dir / "cemetery").exists()

    async def test_cemetery_already_exists(self, isolated_bees_env):
        """Pre-existing cemetery/ should not cause errors."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        # Pre-create cemetery
        (hive_dir / "cemetery").mkdir()

        bee_guid = _make_guid("rst")
        helper.create_ticket(hive_dir, "b.rst", "bee", "Existing Cemetery", guid=bee_guid)

        result = await _undertaker(
            hive_name="test_hive",
            query_yaml="- ['type=bee']",
        )

        assert result["status"] == "success"
        assert result["archived_count"] >= 1
        assert bee_guid in result["archived_guids"]


    async def test_phase2_uses_read_ticket_not_direct_parse(self, isolated_bees_env):
        """Phase 2 calls read_ticket() with file_path into cemetery; _read_guid is gone."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        bee_guid = _make_guid("abc")
        helper.create_ticket(hive_dir, "b.abc", "bee", "Test Bee", guid=bee_guid)

        mock_ticket = MagicMock()
        mock_ticket.guid = bee_guid

        with patch("src.mcp_undertaker.read_ticket", return_value=mock_ticket) as mock_read:
            result = await _undertaker(
                hive_name="test_hive",
                query_yaml="- ['type=bee']",
            )

        assert result["status"] == "success"
        assert mock_read.called
        call_kwargs = mock_read.call_args.kwargs
        assert "file_path" in call_kwargs
        assert "cemetery" in str(call_kwargs["file_path"])

    async def test_phase2_skips_ticket_when_read_ticket_raises(self, isolated_bees_env):
        """When read_ticket raises in Phase 2, the bee is still archived but guid rename is skipped."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        bee_guid = _make_guid("abc")
        helper.create_ticket(hive_dir, "b.abc", "bee", "Test Bee", guid=bee_guid)

        with patch("src.mcp_undertaker.read_ticket", side_effect=Exception("parse error")):
            result = await _undertaker(
                hive_name="test_hive",
                query_yaml="- ['type=bee']",
            )

        assert result["status"] == "success"
        assert result["archived_guids"] == []


class TestUndertakerScheduler:
    """Tests for UndertakerScheduler._fire()."""

    def test_fire_skips_hive_no_longer_in_config(self, tmp_path):
        """_fire() skips archiving when the hive is absent from fresh config (bug b.Qo6)."""
        hive_dir = tmp_path / "test_hive"
        hive_dir.mkdir()

        hive_cfg = HiveConfig(
            path=str(hive_dir),
            display_name="Test Hive",
            created_at="2024-01-01T00:00:00Z",
            undertaker_schedule_seconds=3600,
            undertaker_schedule_query_yaml="- ['status=finished']",
        )
        bees_config = BeesConfig(hives={"test_hive": hive_cfg})
        scheduler = UndertakerScheduler(bees_config, tmp_path)

        # Simulate hive removed from config (e.g. hive deregistered after scheduler started)
        empty_config = BeesConfig(hives={})
        sched = scheduler._schedules[0]

        with patch("src.mcp_undertaker.load_bees_config", return_value=empty_config), \
             patch("src.mcp_undertaker._undertaker_core") as mock_core:
            scheduler._fire(sched)  # must not raise

        mock_core.assert_not_called()

    def test_fire_regenerates_index_after_successful_archival(self, tmp_path):
        """_fire() calls generate_index for the hive after a successful undertaker run."""
        hive_dir = tmp_path / "test_hive"
        hive_dir.mkdir()

        hive_cfg = HiveConfig(
            path=str(hive_dir),
            display_name="Test Hive",
            created_at="2024-01-01T00:00:00Z",
            undertaker_schedule_seconds=3600,
            undertaker_schedule_query_yaml="- ['status=finished']",
        )
        bees_config = BeesConfig(hives={"test_hive": hive_cfg})
        scheduler = UndertakerScheduler(bees_config, tmp_path)
        sched = scheduler._schedules[0]

        success_result = {"status": "success", "archived_count": 2, "archived_guids": ["g1", "g2"], "skipped": []}

        with patch("src.mcp_undertaker.load_bees_config", return_value=bees_config), \
             patch("src.mcp_undertaker._undertaker_core", return_value=success_result), \
             patch("src.mcp_undertaker.generate_index") as mock_idx:
            scheduler._fire(sched)

        mock_idx.assert_called_once_with(hive_name="test_hive")

    def test_fire_skips_index_on_failed_archival(self, tmp_path):
        """_fire() does not call generate_index when the undertaker run fails."""
        hive_dir = tmp_path / "test_hive"
        hive_dir.mkdir()

        hive_cfg = HiveConfig(
            path=str(hive_dir),
            display_name="Test Hive",
            created_at="2024-01-01T00:00:00Z",
            undertaker_schedule_seconds=3600,
            undertaker_schedule_query_yaml="- ['status=finished']",
        )
        bees_config = BeesConfig(hives={"test_hive": hive_cfg})
        scheduler = UndertakerScheduler(bees_config, tmp_path)
        sched = scheduler._schedules[0]

        error_result = {"status": "error", "message": "query failed"}

        with patch("src.mcp_undertaker.load_bees_config", return_value=bees_config), \
             patch("src.mcp_undertaker._undertaker_core", return_value=error_result), \
             patch("src.mcp_undertaker.generate_index") as mock_idx:
            scheduler._fire(sched)

        mock_idx.assert_not_called()

    def test_fire_continues_if_index_regeneration_fails(self, tmp_path):
        """_fire() logs a warning but doesn't raise if generate_index throws."""
        hive_dir = tmp_path / "test_hive"
        hive_dir.mkdir()

        hive_cfg = HiveConfig(
            path=str(hive_dir),
            display_name="Test Hive",
            created_at="2024-01-01T00:00:00Z",
            undertaker_schedule_seconds=3600,
            undertaker_schedule_query_yaml="- ['status=finished']",
            undertaker_schedule_log_path=str(tmp_path / "ut.log"),
        )
        bees_config = BeesConfig(hives={"test_hive": hive_cfg})
        scheduler = UndertakerScheduler(bees_config, tmp_path)
        sched = scheduler._schedules[0]

        success_result = {"status": "success", "archived_count": 1, "archived_guids": ["g1"], "skipped": []}

        with patch("src.mcp_undertaker.load_bees_config", return_value=bees_config), \
             patch("src.mcp_undertaker._undertaker_core", return_value=success_result), \
             patch("src.mcp_undertaker.generate_index", side_effect=RuntimeError("disk full")):
            scheduler._fire(sched)  # must not raise

        # Log file should still have been written (index failure doesn't block logging)
        log_content = (tmp_path / "ut.log").read_text()
        assert "archived=1" in log_content
