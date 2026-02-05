"""File system watcher for automatic index regeneration."""

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from .index_generator import generate_index

logger = logging.getLogger(__name__)


class TicketChangeHandler(FileSystemEventHandler):
    """
    Handler for ticket file changes that triggers index regeneration.

    Monitors .md files in the tickets directory and regenerates index.md
    when changes are detected.
    """

    def __init__(self, debounce_seconds: float = 2.0):
        """
        Initialize handler with debounce settings.

        Args:
            debounce_seconds: Time to wait before regenerating after last change
        """
        super().__init__()
        self.last_change_time = 0
        self.debounce_seconds = debounce_seconds
        self.pending_regeneration = False
        self._timer: threading.Timer | None = None
        self._timer_lock: threading.Lock = threading.Lock()

    def _should_process_event(self, event: FileSystemEvent) -> bool:
        """
        Check if event should trigger index regeneration.

        Args:
            event: File system event

        Returns:
            True if event should be processed
        """
        # Ignore directory events
        if event.is_directory:
            return False

        # Only process .md files
        if not event.src_path.endswith('.md'):
            return False

        # Ignore index.md itself to avoid loops
        if Path(event.src_path).name == 'index.md':
            return False

        return True

    def _do_regeneration(self):
        """Perform the actual index regeneration for all hives."""
        try:
            logger.info("Regenerating indexes due to ticket changes...")
            # generate_index() now handles all hives and writes to their respective index.md files
            generate_index()
            logger.info("Indexes regenerated for all hives")
        except Exception as e:
            logger.error(f"Failed to regenerate indexes: {e}", exc_info=True)
        finally:
            with self._timer_lock:
                self.pending_regeneration = False
                self._timer = None

    def _trigger_regeneration(self):
        """Trigger index regeneration with debouncing using threading.Timer."""
        with self._timer_lock:
            # Cancel any existing timer
            if self._timer is not None:
                self._timer.cancel()

            self.last_change_time = time.time()
            self.pending_regeneration = True

            # Schedule regeneration after debounce period
            self._timer = threading.Timer(self.debounce_seconds, self._do_regeneration)
            self._timer.start()

    def on_created(self, event: FileSystemEvent):
        """Handle file creation events."""
        if self._should_process_event(event):
            logger.debug(f"Ticket created: {event.src_path}")
            self._trigger_regeneration()

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events."""
        if self._should_process_event(event):
            logger.debug(f"Ticket modified: {event.src_path}")
            self._trigger_regeneration()

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion events."""
        if self._should_process_event(event):
            logger.debug(f"Ticket deleted: {event.src_path}")
            self._trigger_regeneration()

    def cleanup(self):
        """
        Cancel any pending timer and cleanup resources.

        This method is safe to call multiple times and handles the case
        where no timer is pending. Should be called before stopping the
        observer to ensure graceful shutdown.
        """
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self.pending_regeneration = False


def start_watcher(debounce_seconds: float = 2.0):
    """
    Start file system watcher for all hive directories.

    Monitors all configured hive directories and automatically regenerates index.md
    files when .md files are created, modified, or deleted.

    Args:
        debounce_seconds: Time to wait before regenerating after last change

    Examples:
        >>> start_watcher()  # Blocks until interrupted
        Watching hive directories for changes...
        ^C

    Raises:
        ValueError: If no hives are configured
    """
    from .config import load_bees_config

    # Load hive configuration
    config = load_bees_config()

    if not config or not config.hives:
        raise ValueError("No hives configured in .bees/config.json. Cannot start watcher.")

    event_handler = TicketChangeHandler(debounce_seconds=debounce_seconds)
    observer = Observer()

    # Watch all hive directories
    watched_dirs = []
    for hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)
        if hive_path.exists():
            observer.schedule(event_handler, str(hive_path), recursive=True)
            watched_dirs.append(str(hive_path))
            logger.info(f"Watching hive: {hive_name} at {hive_path}")

    if not watched_dirs:
        raise ValueError("No valid hive directories found to watch")

    observer.start()

    logger.info(f"Watching {len(watched_dirs)} hive directories for changes (Ctrl+C to stop)...")
    print(f"Watching {len(watched_dirs)} hive directories for changes...")
    print("Press Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
        event_handler.cleanup()
        observer.stop()

    observer.join()
    logger.info("Watcher stopped")
