"""Unit tests for watcher module with threading.Timer debounce behavior."""

import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from watchdog.events import FileSystemEvent, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent

from src.watcher import TicketChangeHandler, start_watcher


class TestTicketChangeHandler:
    """Tests for TicketChangeHandler class."""

    def test_init_creates_timer_attributes(self):
        """Should initialize timer and lock attributes."""
        handler = TicketChangeHandler(debounce_seconds=2.0)

        assert handler.debounce_seconds == 2.0
        assert handler._timer is None
        assert isinstance(handler._timer_lock, type(threading.Lock()))
        assert handler.pending_regeneration is False

    def test_timer_lock_type_annotation(self):
        """Should verify _timer_lock has correct type annotation."""
        handler = TicketChangeHandler()

        # Verify _timer_lock is initialized as threading.Lock
        assert isinstance(handler._timer_lock, threading.Lock)

        # Verify it's a real Lock instance that supports lock operations
        assert hasattr(handler._timer_lock, 'acquire')
        assert hasattr(handler._timer_lock, 'release')
        assert hasattr(handler._timer_lock, '__enter__')
        assert hasattr(handler._timer_lock, '__exit__')

    def test_timer_lock_thread_safety_operations(self):
        """Should verify _timer_lock supports thread-safe context manager operations."""
        handler = TicketChangeHandler()

        # Test context manager protocol
        with handler._timer_lock:
            # Should successfully acquire and release lock
            pass

        # Test explicit acquire/release
        acquired = handler._timer_lock.acquire(blocking=False)
        assert acquired is True
        handler._timer_lock.release()

    def test_should_process_event_rejects_directories(self):
        """Should return False for directory events."""
        handler = TicketChangeHandler()
        event = Mock(spec=FileSystemEvent)
        event.is_directory = True
        event.src_path = "/path/to/dir"

        assert handler._should_process_event(event) is False

    def test_should_process_event_rejects_non_markdown(self):
        """Should return False for non-.md files."""
        handler = TicketChangeHandler()
        event = Mock(spec=FileSystemEvent)
        event.is_directory = False
        event.src_path = "/path/to/file.txt"

        assert handler._should_process_event(event) is False

    def test_should_process_event_rejects_index_md(self):
        """Should return False for index.md to avoid loops."""
        handler = TicketChangeHandler()
        event = Mock(spec=FileSystemEvent)
        event.is_directory = False
        event.src_path = "/path/to/index.md"

        assert handler._should_process_event(event) is False

    def test_should_process_event_accepts_ticket_markdown(self):
        """Should return True for ticket .md files."""
        handler = TicketChangeHandler()
        event = Mock(spec=FileSystemEvent)
        event.is_directory = False
        event.src_path = "/path/to/bees-abc.md"

        assert handler._should_process_event(event) is True

    @patch('src.watcher.threading.Timer')
    def test_trigger_regeneration_creates_timer(self, mock_timer_class):
        """Should create and start threading.Timer when triggered."""
        handler = TicketChangeHandler(debounce_seconds=1.5)
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        handler._trigger_regeneration()

        # Verify Timer was created with correct parameters
        mock_timer_class.assert_called_once()
        args = mock_timer_class.call_args[0]
        assert args[0] == 1.5  # debounce_seconds
        assert callable(args[1])  # callback function

        # Verify Timer was started
        mock_timer.start.assert_called_once()

        # Verify state was updated
        assert handler.pending_regeneration is True
        assert handler._timer == mock_timer

    @patch('src.watcher.threading.Timer')
    def test_trigger_regeneration_cancels_existing_timer(self, mock_timer_class):
        """Should cancel existing timer when new event arrives."""
        handler = TicketChangeHandler(debounce_seconds=1.0)

        # Create first timer
        first_timer = Mock()
        mock_timer_class.return_value = first_timer
        handler._trigger_regeneration()

        # Create second timer (should cancel first)
        second_timer = Mock()
        mock_timer_class.return_value = second_timer
        handler._trigger_regeneration()

        # First timer should have been cancelled
        first_timer.cancel.assert_called_once()

        # Second timer should be started
        second_timer.start.assert_called_once()
        assert handler._timer == second_timer

    @patch('src.watcher.generate_index')
    def test_do_regeneration_writes_index(self, mock_generate):
        """Should generate indexes when timer fires."""
        handler = TicketChangeHandler()

        # Setup mock - generate_index now handles writing internally
        mock_generate.return_value = None

        # Trigger regeneration
        handler._do_regeneration()

        # Verify index was generated (writing happens internally)
        mock_generate.assert_called_once()

        # Verify state was cleaned up
        assert handler.pending_regeneration is False
        assert handler._timer is None

    @patch('src.watcher.generate_index')
    def test_do_regeneration_handles_errors(self, mock_generate):
        """Should log errors during regeneration without crashing."""
        handler = TicketChangeHandler()

        # Make generate_index raise an error
        mock_generate.side_effect = Exception("Test error")

        # Should not raise, just log
        handler._do_regeneration()

        # Verify generate was called (and failed)
        mock_generate.assert_called_once()

    @patch('src.watcher.generate_index')
    def test_do_regeneration_cleans_up_state_on_exception(self, mock_generate):
        """Should clean up timer state even when regeneration raises exception."""
        handler = TicketChangeHandler()

        # Set up initial timer state (simulate timer just fired)
        handler.pending_regeneration = True
        handler._timer = Mock()

        # Make generate_index raise an error
        mock_generate.side_effect = Exception("Test error")

        # Call _do_regeneration - should not raise
        handler._do_regeneration()

        # Verify state was cleaned up despite the exception
        assert handler.pending_regeneration is False
        assert handler._timer is None

    @patch('src.watcher.threading.Timer')
    def test_rapid_file_changes_cancel_and_reschedule(self, mock_timer_class):
        """Should cancel and reschedule timer on rapid successive changes."""
        handler = TicketChangeHandler(debounce_seconds=2.0)

        timers = []
        def create_timer(*args, **kwargs):
            timer = Mock()
            timers.append(timer)
            return timer

        mock_timer_class.side_effect = create_timer

        # Trigger multiple rapid changes
        handler._trigger_regeneration()
        handler._trigger_regeneration()
        handler._trigger_regeneration()

        # All but last timer should be cancelled
        assert timers[0].cancel.call_count == 1
        assert timers[1].cancel.call_count == 1
        assert timers[2].cancel.call_count == 0  # Last timer not cancelled

        # Last timer should be active
        assert handler._timer == timers[2]

    @patch('src.watcher.threading.Timer')
    def test_on_created_triggers_regeneration_for_valid_files(self, mock_timer_class):
        """Should trigger regeneration on ticket file creation."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        event = FileCreatedEvent("/path/to/bees-test.md")
        handler.on_created(event)

        # Verify timer was created and started
        mock_timer.start.assert_called_once()

    @patch('src.watcher.threading.Timer')
    def test_on_modified_triggers_regeneration_for_valid_files(self, mock_timer_class):
        """Should trigger regeneration on ticket file modification."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        event = FileModifiedEvent("/path/to/bees-test.md")
        handler.on_modified(event)

        # Verify timer was created and started
        mock_timer.start.assert_called_once()

    @patch('src.watcher.threading.Timer')
    def test_on_deleted_triggers_regeneration_for_valid_files(self, mock_timer_class):
        """Should trigger regeneration on ticket file deletion."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        event = FileDeletedEvent("/path/to/bees-test.md")
        handler.on_deleted(event)

        # Verify timer was created and started
        mock_timer.start.assert_called_once()

    @patch('src.watcher.threading.Timer')
    def test_events_ignore_non_ticket_files(self, mock_timer_class):
        """Should not trigger regeneration for non-ticket files."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        # Try various non-ticket files (non-.md and index.md specifically)
        event1 = FileCreatedEvent("/path/to/file.txt")
        event2 = FileModifiedEvent("/path/to/index.md")
        event3 = FileDeletedEvent("/path/to/data.json")

        handler.on_created(event1)
        handler.on_modified(event2)
        handler.on_deleted(event3)

        # Timer should never be created
        mock_timer_class.assert_not_called()

    @patch('src.watcher.generate_index')
    def test_debounce_only_regenerates_after_quiet_period(
        self, mock_generate
    ):
        """Should only regenerate once after debounce period with no new changes."""
        handler = TicketChangeHandler(debounce_seconds=0.1)

        # Setup mock
        mock_generate.return_value = None

        # Use real Timer for this integration test (no mocking)
        # Trigger multiple rapid changes
        handler._trigger_regeneration()
        time.sleep(0.05)  # Less than debounce
        handler._trigger_regeneration()
        time.sleep(0.05)  # Less than debounce
        handler._trigger_regeneration()

        # Wait for debounce period to complete
        time.sleep(0.15)

        # Should only generate once (after last change)
        assert mock_generate.call_count == 1

    def test_timer_lock_provides_thread_safety(self):
        """Should use lock to protect timer operations."""
        handler = TicketChangeHandler()

        # Verify lock exists and is a threading.Lock
        assert hasattr(handler, '_timer_lock')
        assert isinstance(handler._timer_lock, type(threading.Lock()))

    @patch('src.watcher.threading.Timer')
    def test_cleanup_cancels_pending_timer(self, mock_timer_class):
        """Should cancel pending timer when cleanup is called."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        # Trigger regeneration to create a timer
        handler._trigger_regeneration()
        assert handler._timer == mock_timer
        assert handler.pending_regeneration is True

        # Call cleanup
        handler.cleanup()

        # Verify timer was cancelled and state was cleared
        mock_timer.cancel.assert_called_once()
        assert handler._timer is None
        assert handler.pending_regeneration is False

    def test_cleanup_safe_when_no_timer_pending(self):
        """Should be safe to call cleanup when no timer is pending."""
        handler = TicketChangeHandler()
        assert handler._timer is None

        # Should not raise an error
        handler.cleanup()

        # State should remain clean
        assert handler._timer is None
        assert handler.pending_regeneration is False

    @patch('src.watcher.threading.Timer')
    def test_cleanup_can_be_called_multiple_times(self, mock_timer_class):
        """Should be safe to call cleanup multiple times."""
        handler = TicketChangeHandler()
        mock_timer = Mock()
        mock_timer_class.return_value = mock_timer

        # Trigger regeneration
        handler._trigger_regeneration()

        # Call cleanup multiple times
        handler.cleanup()
        handler.cleanup()
        handler.cleanup()

        # Timer should only be cancelled once (it's None after first cleanup)
        mock_timer.cancel.assert_called_once()
        assert handler._timer is None

    @patch('src.watcher.generate_index')
    def test_timer_does_not_fire_after_cleanup(self, mock_generate):
        """Should ensure timer does not fire after cleanup is called."""
        handler = TicketChangeHandler(debounce_seconds=0.1)

        # Setup mock
        mock_generate.return_value = None

        # Trigger regeneration with real timer
        handler._trigger_regeneration()
        assert handler._timer is not None

        # Call cleanup before timer fires
        handler.cleanup()

        # Wait for what would have been the timer firing
        time.sleep(0.15)

        # Verify generate_index was NOT called (timer was cancelled)
        mock_generate.assert_not_called()

    @patch('src.watcher.threading.Timer')
    def test_concurrent_trigger_regeneration_thread_safety(self, mock_timer_class):
        """Should handle concurrent calls to _trigger_regeneration from multiple threads."""
        handler = TicketChangeHandler(debounce_seconds=1.0)

        # Track all created timers
        timers = []
        timer_lock = threading.Lock()

        def create_timer(*args, **kwargs):
            timer = Mock()
            with timer_lock:
                timers.append(timer)
            return timer

        mock_timer_class.side_effect = create_timer

        # Spawn multiple threads calling _trigger_regeneration concurrently
        num_threads = 10
        threads = []
        barrier = threading.Barrier(num_threads)  # Sync all threads to start together

        def trigger_with_barrier():
            barrier.wait()  # Wait for all threads to be ready
            handler._trigger_regeneration()

        for _ in range(num_threads):
            thread = threading.Thread(target=trigger_with_barrier)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify thread safety conditions:
        # 1. Only one timer should remain active (not cancelled)
        assert handler._timer is not None
        assert handler._timer in timers

        # 2. State should be consistent
        assert handler.pending_regeneration is True

        # 3. All other timers should have been cancelled
        cancelled_count = sum(1 for timer in timers if timer.cancel.called)
        active_count = sum(1 for timer in timers if not timer.cancel.called)

        # Exactly one timer should remain uncancelled
        assert active_count == 1, f"Expected 1 active timer, got {active_count}"
        assert cancelled_count == len(timers) - 1, \
            f"Expected {len(timers) - 1} cancelled timers, got {cancelled_count}"

        # 4. Verify the active timer is the one stored in handler
        assert handler._timer.cancel.call_count == 0


class TestStartWatcherWithHives:
    """Tests for start_watcher() function with hive support."""

    def test_start_watcher_raises_when_no_hives_configured(self, tmp_path, monkeypatch):
        """Should raise ValueError when no hives are configured."""
        monkeypatch.chdir(tmp_path)

        # No .bees/config.json - no hives configured
        with pytest.raises(ValueError, match="No hives configured"):
            start_watcher(debounce_seconds=2.0)

    @patch('src.watcher.Observer')
    def test_start_watcher_watches_all_hive_directories(self, mock_observer_class, tmp_path, monkeypatch):
        """Should watch all configured hive directories."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive directories
        backend_dir = tmp_path / "backend"
        frontend_dir = tmp_path / "frontend"
        backend_dir.mkdir()
        frontend_dir.mkdir()

        # Configure hives
        config = BeesConfig(
            hives={
                "backend": HiveConfig(path=str(backend_dir), display_name="Backend"),
                "frontend": HiveConfig(path=str(frontend_dir), display_name="Frontend"),
            }
        )
        save_bees_config(config)

        # Mock observer
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        # Mock start() to raise KeyboardInterrupt immediately (to exit the while loop)
        mock_observer.start.side_effect = KeyboardInterrupt()

        # Call start_watcher
        try:
            start_watcher(debounce_seconds=2.0)
        except KeyboardInterrupt:
            pass

        # Verify observer.schedule was called for each hive
        assert mock_observer.schedule.call_count == 2

    @patch('src.watcher.Observer')
    def test_start_watcher_skips_nonexistent_hive_paths(self, mock_observer_class, tmp_path, monkeypatch):
        """Should skip hives with nonexistent paths."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create only one hive directory
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()

        # Configure hives - frontend path doesn't exist
        config = BeesConfig(
            hives={
                "backend": HiveConfig(path=str(backend_dir), display_name="Backend"),
                "frontend": HiveConfig(path=str(tmp_path / "nonexistent"), display_name="Frontend"),
            }
        )
        save_bees_config(config)

        # Mock observer
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        mock_observer.start.side_effect = KeyboardInterrupt()

        # Call start_watcher
        try:
            start_watcher(debounce_seconds=2.0)
        except KeyboardInterrupt:
            pass

        # Verify observer.schedule was called only once (for backend)
        assert mock_observer.schedule.call_count == 1

    @patch('src.watcher.Observer')
    def test_start_watcher_raises_when_no_valid_hive_paths(self, mock_observer_class, tmp_path, monkeypatch):
        """Should raise ValueError when no valid hive directories exist."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Configure hives with nonexistent paths
        config = BeesConfig(
            hives={
                "backend": HiveConfig(path=str(tmp_path / "nonexistent1"), display_name="Backend"),
                "frontend": HiveConfig(path=str(tmp_path / "nonexistent2"), display_name="Frontend"),
            }
        )
        save_bees_config(config)

        # Should raise ValueError
        with pytest.raises(ValueError, match="No valid hive directories found"):
            start_watcher(debounce_seconds=2.0)
