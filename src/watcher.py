"""File system watcher for automatic index regeneration."""

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from .index_generator import generate_index
from .paths import get_index_path, TICKETS_DIR

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
        """Perform the actual index regeneration."""
        try:
            logger.info("Regenerating index due to ticket changes...")
            index_content = generate_index()
            index_path = get_index_path()
            index_path.write_text(index_content)
            logger.info(f"Index regenerated: {index_path}")
        except Exception as e:
            logger.error(f"Failed to regenerate index: {e}", exc_info=True)
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


def start_watcher(tickets_dir: Path = TICKETS_DIR, debounce_seconds: float = 2.0):
    """
    Start file system watcher for tickets directory.

    Monitors the tickets directory and automatically regenerates index.md
    when .md files are created, modified, or deleted.

    Args:
        tickets_dir: Path to tickets directory to watch
        debounce_seconds: Time to wait before regenerating after last change

    Examples:
        >>> start_watcher()  # Blocks until interrupted
        Watching /path/to/tickets for changes...
        ^C
    """
    if not tickets_dir.exists():
        raise FileNotFoundError(f"Tickets directory not found: {tickets_dir}")

    event_handler = TicketChangeHandler(debounce_seconds=debounce_seconds)
    observer = Observer()
    observer.schedule(event_handler, str(tickets_dir), recursive=True)
    observer.start()

    logger.info(f"Watching {tickets_dir} for changes (Ctrl+C to stop)...")
    print(f"Watching {tickets_dir} for changes...")
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
