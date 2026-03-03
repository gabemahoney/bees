"""
Unit tests for filesystem watcher and auto-linting.

PURPOSE:
Tests the file watcher that monitors ticket directories for changes and
automatically triggers linting with debouncing via threading.Timer.

SCOPE - Tests that belong here:
- TicketChangeHandler: Filesystem event handling
- start_watcher(): Watcher initialization and lifecycle
- Debouncing logic (threading.Timer based)
- Event handling: file created, modified, deleted
- Auto-linting triggers
- Debounce delay behavior
- Watcher cleanup and shutdown

SCOPE - Tests that DON'T belong here:
- Linter execution -> test_linter.py
- File operations -> test_reader.py, test_writer_factory.py
- Index generation -> test_index_generator.py

RELATED FILES:
- test_linter.py: Linter triggered by watcher
- test_index_generator.py: Index regeneration after changes
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest
from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent, FileSystemEvent

from src.repo_context import repo_root_context
from src.watcher import TicketChangeHandler, start_watcher
from tests.conftest import write_scoped_config


class TestTicketChangeHandler:
    """Tests for TicketChangeHandler class."""

    def test_init_creates_timer_attributes(self):
        """Should initialize timer and lock attributes."""
        handler = TicketChangeHandler(debounce_seconds=2.0)

        assert handler.debounce_seconds == 2.0
        assert handler._timer is None
        assert isinstance(handler._timer_lock, type(threading.Lock()))
        assert handler.pending_regeneration is False

    @pytest.mark.parametrize(
        "is_directory, src_path, expected",
        [
            (True, "/path/to/dir", False),
            (False, "/path/to/file.txt", False),
            (False, "/path/to/index.md", False),
            (False, "/path/to/b.abc.md", True),
        ],
        ids=["directory", "non-markdown", "index-md", "ticket-markdown"],
    )
    def test_should_process_event(self, is_directory, src_path, expected):
        """Should correctly filter events by type and file extension."""
        handler = TicketChangeHandler()
        event = Mock(spec=FileSystemEvent)
        event.is_directory = is_directory
        event.src_path = src_path

        assert handler._should_process_event(event) is expected

    @patch("src.watcher.threading.Timer")
    def test_trigger_regeneration_creates_timer(self, mock_timer_class):
        """Should create and start threading.Timer when triggered."""
        handler = TicketChangeHandler(debounce_seconds=1.5)
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        handler._trigger_regeneration()

        mock_timer_class.assert_called_once()
        args = mock_timer_class.call_args[0]
        assert args[0] == 1.5
        assert callable(args[1])

        mock_timer.start.assert_called_once()
        assert handler.pending_regeneration is True
        assert handler._timer == mock_timer

    @patch("src.watcher.generate_index")
    @patch("src.config.load_bees_config")
    @patch("src.linter.Linter")
    def test_do_regeneration_writes_index(self, mock_linter_class, mock_load_config, mock_generate):
        """Should run linter then generate indexes when timer fires."""
        handler = TicketChangeHandler()

        # Mock config with hives
        mock_config = Mock()
        mock_hive = Mock()
        mock_hive.path = "/fake/hive/path"
        mock_config.hives = {"test_hive": mock_hive}
        mock_load_config.return_value = mock_config

        # Mock linter
        mock_linter = Mock()
        mock_report = Mock()
        mock_report.errors = []
        mock_linter.run.return_value = mock_report
        mock_linter_class.return_value = mock_linter

        mock_generate.return_value = None

        handler._do_regeneration()

        mock_linter_class.assert_called_once()
        mock_linter.run.assert_called_once()
        mock_generate.assert_called_once()
        assert handler.pending_regeneration is False
        assert handler._timer is None

    @patch("src.watcher.generate_index")
    @patch("src.config.load_bees_config")
    def test_do_regeneration_handles_errors_and_cleans_state(self, mock_load_config, mock_generate):
        """Should log errors during regeneration without crashing, cleaning up state."""
        handler = TicketChangeHandler()
        handler.pending_regeneration = True
        handler._timer = Mock()

        # Mock config with no hives to skip linter
        mock_config = Mock()
        mock_config.hives = {}
        mock_load_config.return_value = mock_config

        mock_generate.side_effect = Exception("Test error")

        handler._do_regeneration()

        mock_generate.assert_called_once()
        assert handler.pending_regeneration is False
        assert handler._timer is None

    @patch("src.watcher.threading.Timer")
    def test_rapid_file_changes_cancel_and_reschedule(self, mock_timer_class):
        """Should cancel and reschedule timer on rapid successive changes."""
        handler = TicketChangeHandler(debounce_seconds=2.0)

        timers = []

        def create_timer(*args, **kwargs):
            timer = Mock()
            timers.append(timer)
            return timer

        mock_timer_class.side_effect = create_timer

        handler._trigger_regeneration()
        handler._trigger_regeneration()
        handler._trigger_regeneration()

        assert timers[0].cancel.call_count == 1
        assert timers[1].cancel.call_count == 1
        assert timers[2].cancel.call_count == 0
        assert handler._timer == timers[2]

    @pytest.mark.parametrize(
        "event_class, handler_method",
        [
            (FileCreatedEvent, "on_created"),
            (FileModifiedEvent, "on_modified"),
            (FileDeletedEvent, "on_deleted"),
        ],
    )
    @patch("src.watcher.threading.Timer")
    def test_file_events_trigger_regeneration(self, mock_timer_class, event_class, handler_method):
        """Should trigger regeneration on ticket file creation/modification/deletion."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        event = event_class("/path/to/b.tst.md")
        getattr(handler, handler_method)(event)

        mock_timer.start.assert_called_once()

    @patch("src.watcher.generate_index")
    @patch("src.config.load_bees_config")
    def test_debounce_only_regenerates_after_quiet_period(self, mock_load_config, mock_generate):
        """Should only regenerate once after debounce period with no new changes."""
        handler = TicketChangeHandler(debounce_seconds=0.1)

        # Mock config with no hives to skip linter
        mock_config = Mock()
        mock_config.hives = {}
        mock_load_config.return_value = mock_config

        mock_generate.return_value = None

        handler._trigger_regeneration()
        time.sleep(0.05)
        handler._trigger_regeneration()
        time.sleep(0.05)
        handler._trigger_regeneration()

        time.sleep(0.15)

        assert mock_generate.call_count == 1

    @patch("src.watcher.threading.Timer")
    def test_cleanup_cancels_pending_timer(self, mock_timer_class):
        """Should cancel pending timer when cleanup is called."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        handler._trigger_regeneration()
        assert handler._timer == mock_timer
        assert handler.pending_regeneration is True

        handler.cleanup()

        mock_timer.cancel.assert_called_once()
        assert handler._timer is None
        assert handler.pending_regeneration is False

    @patch("src.watcher.threading.Timer")
    def test_concurrent_trigger_regeneration_thread_safety(self, mock_timer_class):
        """Should handle concurrent calls to _trigger_regeneration from multiple threads."""
        handler = TicketChangeHandler(debounce_seconds=1.0)

        timers = []
        timer_lock = threading.Lock()

        def create_timer(*args, **kwargs):
            timer = Mock()
            with timer_lock:
                timers.append(timer)
            return timer

        mock_timer_class.side_effect = create_timer

        num_threads = 10
        barrier = threading.Barrier(num_threads)

        def trigger_with_barrier():
            barrier.wait()
            handler._trigger_regeneration()

        threads = [threading.Thread(target=trigger_with_barrier) for _ in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert handler._timer is not None
        assert handler.pending_regeneration is True

        cancelled_count = sum(1 for timer in timers if timer.cancel.called)
        active_count = sum(1 for timer in timers if not timer.cancel.called)

        assert active_count == 1, f"Expected 1 active timer, got {active_count}"
        assert cancelled_count == len(timers) - 1
        assert handler._timer.cancel.call_count == 0


class TestStartWatcherWithHives:
    """Tests for start_watcher() function with hive support."""

    def test_start_watcher_raises_when_no_hives_configured(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should raise ValueError when no hives are configured."""
        monkeypatch.chdir(tmp_path)
        write_scoped_config(mock_global_bees_dir, tmp_path, {
            "hives": {},
            "child_tiers": {},
        })

        with repo_root_context(tmp_path):
            with pytest.raises(ValueError, match="No hives configured"):
                start_watcher(debounce_seconds=2.0)

    @patch("src.watcher.Observer")
    def test_start_watcher_watches_all_hive_directories(
        self, mock_observer_class, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Should watch all configured hive directories recursively."""
        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        frontend_dir = tmp_path / "frontend"
        backend_dir.mkdir()
        frontend_dir.mkdir()

        write_scoped_config(
            mock_global_bees_dir,
            tmp_path,
            {
                "hives": {
                    "backend": {
                        "path": str(backend_dir),
                        "display_name": "Backend",
                        "created_at": "2026-02-02T10:00:00",
                    },
                    "frontend": {
                        "path": str(frontend_dir),
                        "display_name": "Frontend",
                        "created_at": "2026-02-02T10:00:00",
                    },
                },
                "child_tiers": {},
            },
        )

        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        mock_observer.start.side_effect = KeyboardInterrupt()

        with repo_root_context(tmp_path):
            try:
                start_watcher(debounce_seconds=2.0)
            except KeyboardInterrupt:
                pass

        assert mock_observer.schedule.call_count == 2
        # Verify recursive=True is set for hierarchical storage
        for call_args in mock_observer.schedule.call_args_list:
            args, kwargs = call_args
            assert kwargs.get('recursive') or args[2] is True

    @patch("src.watcher.Observer")
    def test_start_watcher_skips_nonexistent_hive_paths(
        self, mock_observer_class, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Should skip hives with nonexistent paths."""
        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()

        write_scoped_config(
            mock_global_bees_dir,
            tmp_path,
            {
                "hives": {
                    "backend": {
                        "path": str(backend_dir),
                        "display_name": "Backend",
                        "created_at": "2026-02-02T10:00:00",
                    },
                    "frontend": {
                        "path": str(tmp_path / "nonexistent"),
                        "display_name": "Frontend",
                        "created_at": "2026-02-02T10:00:00",
                    },
                },
                "child_tiers": {},
            },
        )

        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        mock_observer.start.side_effect = KeyboardInterrupt()

        with repo_root_context(tmp_path):
            try:
                start_watcher(debounce_seconds=2.0)
            except KeyboardInterrupt:
                pass

        assert mock_observer.schedule.call_count == 1

    @patch("src.watcher.Observer")
    def test_start_watcher_raises_when_no_valid_hive_paths(
        self, mock_observer_class, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Should raise ValueError when no valid hive directories exist."""
        monkeypatch.chdir(tmp_path)

        write_scoped_config(
            mock_global_bees_dir,
            tmp_path,
            {
                "hives": {
                    "backend": {
                        "path": str(tmp_path / "nonexistent1"),
                        "display_name": "Backend",
                        "created_at": "2026-02-02T10:00:00",
                    },
                    "frontend": {
                        "path": str(tmp_path / "nonexistent2"),
                        "display_name": "Frontend",
                        "created_at": "2026-02-02T10:00:00",
                    },
                },
                "child_tiers": {},
            },
        )

        with repo_root_context(tmp_path):
            with pytest.raises(ValueError, match="No valid hive directories found"):
                start_watcher(debounce_seconds=2.0)


class TestWatcherHierarchicalStorage:
    """Tests for watcher with hierarchical directory structure."""

    @patch("src.watcher.threading.Timer")
    def test_watcher_detects_changes_in_nested_directories(self, mock_timer_class):
        """Should trigger regeneration when files change in nested ticket directories."""
        handler = TicketChangeHandler(debounce_seconds=1.0)
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        # Simulate file change in nested directory: b.Amx/t1.X4F/t1.X4F.md
        event = FileModifiedEvent("/path/to/backend/b.Amx/t1.X4F/t1.X4F.md")
        handler.on_modified(event)

        mock_timer.start.assert_called_once()
        assert handler.pending_regeneration is True

    @patch("src.watcher.threading.Timer")
    def test_watcher_detects_deeply_nested_changes(self, mock_timer_class):
        """Should detect changes in deeply nested ticket hierarchies."""
        handler = TicketChangeHandler(debounce_seconds=1.0)
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        # Simulate deeply nested: b.Amx/t1.X4F/t2.Y8G/t2.Y8G.md
        event = FileCreatedEvent("/path/to/backend/b.Amx/t1.X4F/t2.Y8G/t2.Y8G.md")
        handler.on_created(event)

        mock_timer.start.assert_called_once()

    @patch("src.watcher.generate_index")
    @patch("src.config.load_bees_config")
    def test_debouncing_with_nested_file_moves(self, mock_load_config, mock_generate):
        """Should debounce when files are moved between nested directories."""
        handler = TicketChangeHandler(debounce_seconds=0.1)

        # Mock config with no hives to skip linter
        mock_config = Mock()
        mock_config.hives = {}
        mock_load_config.return_value = mock_config

        mock_generate.return_value = None

        # Simulate linter moving file from flat to nested structure
        # Delete event: backend/t1.X4F.md
        event_delete = FileDeletedEvent("/path/to/backend/t1.X4F.md")
        handler.on_deleted(event_delete)

        time.sleep(0.05)

        # Create event: backend/b.Amx/t1.X4F/t1.X4F.md
        event_create = FileCreatedEvent("/path/to/backend/b.Amx/t1.X4F/t1.X4F.md")
        handler.on_created(event_create)

        # Wait for debounce period
        time.sleep(0.15)

        # Should only regenerate once after both events
        assert mock_generate.call_count == 1

    @patch("src.watcher.threading.Timer")
    def test_watcher_ignores_non_hierarchical_md_files(self, mock_timer_class):
        """Should process all .md files except index.md, trusting list_tickets() to filter."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        # File in ticket directory - should process
        event1 = FileModifiedEvent("/path/to/backend/b.Amx/b.Amx.md")
        handler.on_modified(event1)
        assert mock_timer.start.call_count == 1

        # Random .md file - should process (list_tickets filters later)
        event2 = FileModifiedEvent("/path/to/backend/notes.md")
        handler.on_modified(event2)
        assert mock_timer.start.call_count == 2

        # index.md - should skip
        event3 = FileModifiedEvent("/path/to/backend/index.md")
        handler.on_modified(event3)
        assert mock_timer.start.call_count == 2  # No change

    @patch("src.watcher.threading.Timer")
    def test_rapid_nested_changes_cancel_and_reschedule(self, mock_timer_class):
        """Should handle rapid changes across nested directories with proper debouncing."""
        handler = TicketChangeHandler(debounce_seconds=2.0)

        timers = []

        def create_timer(*args, **kwargs):
            timer = Mock()
            timers.append(timer)
            return timer

        mock_timer_class.side_effect = create_timer

        # Multiple rapid changes in different nested locations
        handler._trigger_regeneration()  # Change in b.Amx/b.Amx.md
        handler._trigger_regeneration()  # Change in b.Amx/t1.X4F/t1.X4F.md
        handler._trigger_regeneration()  # Change in b.Def/b.Def.md

        # All but the last timer should be cancelled
        assert timers[0].cancel.call_count == 1
        assert timers[1].cancel.call_count == 1
        assert timers[2].cancel.call_count == 0
        assert handler._timer == timers[2]


class TestWatcherLinterIntegration:
    """Integration tests for watcher-linter pipeline."""

    @patch("src.watcher.generate_index")
    @patch("src.linter.Linter")
    @patch("src.config.load_bees_config")
    def test_pipeline_ordering_linter_before_index(self, mock_load_config, mock_linter_class, mock_generate):
        """Should run linter BEFORE index generation to ensure correct execution order."""
        handler = TicketChangeHandler(debounce_seconds=0.1)

        # Mock config with single hive
        mock_config = Mock()
        mock_hive = Mock()
        mock_hive.path = "/fake/hive"
        mock_config.hives = {"test": mock_hive}
        mock_load_config.return_value = mock_config

        # Mock linter
        mock_linter = Mock()
        mock_report = Mock()
        mock_report.errors = []
        mock_linter.run.return_value = mock_report
        mock_linter_class.return_value = mock_linter

        # Track call order
        call_order = []
        mock_linter.run.side_effect = lambda: call_order.append("linter")
        mock_generate.side_effect = lambda: call_order.append("index")

        handler._do_regeneration()

        # Verify linter was called before index generation
        assert call_order == ["linter", "index"]
        mock_linter_class.assert_called_once_with(
            tickets_dir="/fake/hive",
            hive_name="test",
            auto_fix=True
        )
        mock_generate.assert_called_once()

    @patch("src.watcher.generate_index")
    @patch("src.linter.Linter")
    @patch("src.config.load_bees_config")
    def test_linter_moves_trigger_debounce_and_settle(self, mock_load_config, mock_linter_class, mock_generate):
        """Should handle linter-triggered file moves with debounce, eventually settling without infinite loop."""
        handler = TicketChangeHandler(debounce_seconds=0.1)

        # Mock config
        mock_config = Mock()
        mock_hive = Mock()
        mock_hive.path = "/fake/hive"
        mock_config.hives = {"test": mock_hive}
        mock_load_config.return_value = mock_config

        # Mock linter - first run triggers file move, second run is stable
        mock_linter = Mock()
        mock_report = Mock()
        mock_report.errors = []

        # Track number of linter runs
        linter_run_count = [0]

        def linter_run_side_effect():
            linter_run_count[0] += 1
            return mock_report

        mock_linter.run.side_effect = linter_run_side_effect
        mock_linter_class.return_value = mock_linter

        # First trigger: simulates file change
        handler._trigger_regeneration()
        time.sleep(0.15)  # Wait for debounce + execution

        # Verify first run completed
        assert linter_run_count[0] == 1
        assert mock_generate.call_count == 1

        # Simulate linter-triggered file move (delete + create)
        event_delete = FileDeletedEvent("/fake/hive/t1.X4F.md")
        handler.on_deleted(event_delete)
        event_create = FileCreatedEvent("/fake/hive/b.Amx/t1.X4F/t1.X4F.md")
        handler.on_created(event_create)

        time.sleep(0.15)  # Wait for second debounce

        # Verify second run completed
        assert linter_run_count[0] == 2
        assert mock_generate.call_count == 2

        # No more events should occur (settled)
        time.sleep(0.15)
        assert linter_run_count[0] == 2  # No additional runs
        assert mock_generate.call_count == 2

    @patch("src.watcher.generate_index")
    @patch("src.linter.Linter")
    @patch("src.config.load_bees_config")
    def test_linter_error_isolation_per_hive(self, mock_load_config, mock_linter_class, mock_generate):
        """Should isolate linter errors per hive, continuing to other hives and index generation."""
        handler = TicketChangeHandler()

        # Mock config with 3 hives
        mock_config = Mock()
        mock_hive1 = Mock()
        mock_hive1.path = "/fake/hive1"
        mock_hive2 = Mock()
        mock_hive2.path = "/fake/hive2"
        mock_hive3 = Mock()
        mock_hive3.path = "/fake/hive3"
        mock_config.hives = {
            "hive1": mock_hive1,
            "hive2": mock_hive2,
            "hive3": mock_hive3,
        }
        mock_load_config.return_value = mock_config

        # Track linter calls and make hive2 fail
        linter_calls = []

        def create_linter(tickets_dir, hive_name, auto_fix):
            mock_linter = Mock()
            linter_calls.append(hive_name)

            if hive_name == "hive2":
                # Hive2 linter fails
                mock_linter.run.side_effect = Exception("Linter error for hive2")
            else:
                # Other hives succeed
                mock_report = Mock()
                mock_report.errors = []
                mock_linter.run.return_value = mock_report

            return mock_linter

        mock_linter_class.side_effect = create_linter
        mock_generate.return_value = None

        handler._do_regeneration()

        # Verify all 3 hives were attempted
        assert sorted(linter_calls) == ["hive1", "hive2", "hive3"]

        # Verify index generation still ran despite hive2 failure
        mock_generate.assert_called_once()

    @patch("src.watcher.generate_index")
    @patch("src.linter.Linter")
    @patch("src.config.load_bees_config")
    @pytest.mark.parametrize(
        "scenario_name, hive_configs, expected_linter_calls",
        [
            pytest.param(
                "single_hive",
                {"backend": Mock(path="/fake/backend")},
                ["backend"],
                id="single_hive",
            ),
            pytest.param(
                "multi_hive",
                {
                    "backend": Mock(path="/fake/backend"),
                    "frontend": Mock(path="/fake/frontend"),
                    "docs": Mock(path="/fake/docs"),
                },
                ["backend", "docs", "frontend"],
                id="multi_hive",
            ),
        ],
    )
    def test_pipeline_runs_on_all_configured_hives(
        self, mock_load_config, mock_linter_class, mock_generate, scenario_name, hive_configs, expected_linter_calls
    ):
        """Should run linter and index generation for all configured hives."""
        handler = TicketChangeHandler()

        # Mock config
        mock_config = Mock()
        mock_config.hives = hive_configs
        mock_load_config.return_value = mock_config

        # Track linter calls
        linter_calls = []

        def create_linter(tickets_dir, hive_name, auto_fix):
            mock_linter = Mock()
            linter_calls.append(hive_name)
            mock_report = Mock()
            mock_report.errors = []
            mock_linter.run.return_value = mock_report
            return mock_linter

        mock_linter_class.side_effect = create_linter
        mock_generate.return_value = None

        handler._do_regeneration()

        # Verify all hives were linted
        assert sorted(linter_calls) == sorted(expected_linter_calls)

        # Verify auto_fix=True was used
        for call_args in mock_linter_class.call_args_list:
            assert call_args[1]["auto_fix"] is True

        # Verify index generation ran once (handles all hives)
        mock_generate.assert_called_once()
