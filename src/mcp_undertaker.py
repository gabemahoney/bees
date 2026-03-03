"""
Undertaker MCP Tool — archives bee tickets and their descendants to /cemetery.

Two-phase archival:
  Phase 1 (atomic mv): Move each matched bee's directory tree into /cemetery.
          If any move fails, return error immediately.
  Phase 2 (best-effort rename): Within cemetery, rename ticket dirs and files
          from {tier}.{shortID} to {tier}.{guid} using the guid from frontmatter.
          Failures are logged and skipped.

MANUAL USE
----------
Call the `undertaker` MCP tool directly to archive bees matching a query:

    undertaker(hive_name="bugs", query_yaml="- ['status=finished']")
    undertaker(hive_name="bugs", query_name="finished_bugs")

Exactly one of query_yaml or query_name must be provided.

SCHEDULED USE
-------------
To automatically archive bees on a recurring schedule, add an
`undertaker_schedule` block to the hive in ~/.bees/config.json:

    {
      "hives": {
        "bugs": {
          "path": "/path/to/hive",
          "undertaker_schedule": {
            "interval_seconds": 3600,
            "query_yaml": "- ['status=finished']",
            "log_path": "/tmp/undertaker-bugs.log"
          }
        }
      }
    }

Config fields:
  interval_seconds  (required) — how often to run, in seconds
  query_yaml        (required if no query_name) — inline YAML query pipeline
  query_name        (required if no query_yaml) — name of a saved named query
  log_path          (optional) — append each run result to this file

The scheduler starts automatically with the MCP server and runs in a
background daemon thread. Restart the server after changing this config.
"""

import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BeesConfig, load_bees_config, load_global_config, resolve_named_query
from .id_utils import is_ticket_id
from .index_generator import generate_index
from .paths import find_ticket_file
from .pipeline import PipelineEvaluator
from .query_parser import QueryParser
from .reader import read_ticket
from .repo_context import get_repo_root, repo_root_context

logger = logging.getLogger(__name__)


def _undertaker_core(
    hive_name: str,
    query_yaml: str | None = None,
    query_name: str | None = None,
) -> dict[str, Any]:
    """Synchronous core of the undertaker — runs inside an active repo_root_context.

    Args:
        hive_name: Hive to operate on (required)
        query_yaml: YAML string for freeform query (mutually exclusive with query_name)
        query_name: Name of a registered query (mutually exclusive with query_yaml)

    Returns:
        dict with status, archived_count, archived_guids, skipped
    """
    # ── Step 1: Validate params ──────────────────────────────────────────
    if query_yaml and query_name:
        return {
            "status": "error",
            "message": "Provide either query_yaml or query_name, not both.",
        }
    if not query_yaml and not query_name:
        return {
            "status": "error",
            "message": "Provide either query_yaml or query_name.",
        }

    # ── Validate hive ────────────────────────────────────────────────────
    config = load_bees_config()
    if not config or not config.hives:
        return {"status": "error", "message": "No hives configured."}

    if hive_name not in config.hives:
        available = sorted(config.hives.keys())
        return {
            "status": "error",
            "message": f"Hive not found: {hive_name}. Available: {', '.join(available)}",
        }

    hive_path = Path(config.hives[hive_name].path)

    # ── Step 2: Execute query ────────────────────────────────────────────
    try:
        if query_name:
            repo_root = get_repo_root()
            global_config = load_global_config()
            resolution = resolve_named_query(query_name, repo_root, global_config)
            if resolution["status"] == "out_of_scope":
                return {
                    "status": "error",
                    "error_type": "query_out_of_scope",
                    "message": f"Query '{query_name}' exists but is not accessible from the current scope.",
                }
            if resolution["status"] == "not_found":
                return {
                    "status": "error",
                    "error_type": "query_not_found",
                    "message": f"Query not found: {query_name}",
                }
            stages = resolution["stages"]
        else:
            parser = QueryParser()
            stages = parser.parse_and_validate(query_yaml)
    except Exception as e:
        return {"status": "error", "message": f"Query error: {e}"}

    try:
        evaluator = PipelineEvaluator()
        result_ids = evaluator.execute_query(stages)
        result_ids = {tid for tid in result_ids if evaluator.tickets.get(tid, {}).get("hive") == hive_name}
    except Exception as e:
        return {"status": "error", "message": f"Query execution failed: {e}"}

    if not result_ids:
        return {
            "status": "success",
            "archived_count": 0,
            "archived_guids": [],
            "skipped": [],
        }

    # ── Step 3: Filter to bees only ──────────────────────────────────────
    bee_ids = sorted(tid for tid in result_ids if tid.startswith("b."))
    skipped = sorted(tid for tid in result_ids if not tid.startswith("b."))

    if not bee_ids:
        return {
            "status": "success",
            "archived_count": 0,
            "archived_guids": [],
            "skipped": skipped,
        }

    # ── Step 4: Phase 1 — atomic mv ─────────────────────────────────────
    cemetery_dir = hive_path / "cemetery"
    cemetery_dir.mkdir(exist_ok=True)

    moved_bees: list[tuple[str, Path]] = []  # (bee_id, cemetery_dest)
    for bee_id in bee_ids:
        ticket_file = find_ticket_file(hive_path, bee_id)
        if not ticket_file:
            return {
                "status": "error",
                "message": f"Phase 1 failed: directory for bee '{bee_id}' not found in hive.",
            }

        bee_dir = ticket_file.parent
        dest = cemetery_dir / bee_dir.name
        try:
            shutil.move(str(bee_dir), str(dest))
            moved_bees.append((bee_id, dest))
        except Exception as e:
            return {
                "status": "error",
                "message": f"Phase 1 failed: could not move '{bee_id}': {e}",
            }

    # ── Step 5: Phase 2 — best-effort rename ────────────────────────────
    archived_count = 0
    archived_guids: list[str] = []

    for _bee_id, subtree_root in moved_bees:
        # Walk bottom-up so child renames complete before parents
        for dirpath, _dirs, files in os.walk(str(subtree_root), topdown=False):
            dir_name = Path(dirpath).name
            if not is_ticket_id(dir_name):
                continue

            md_name = f"{dir_name}.md"
            if md_name not in files:
                continue

            # This is a ticket directory — count it
            archived_count += 1

            # Read guid from frontmatter
            md_path = Path(dirpath) / md_name
            try:
                ticket = read_ticket(ticket_id=dir_name, file_path=md_path)
                guid = ticket.guid
            except Exception as e:
                logger.warning("undertaker: could not read ticket %s: %s", dir_name, e)
                continue

            if not guid:
                continue

            archived_guids.append(guid)

            # Rename file and directory
            tier_prefix = dir_name.split(".")[0]  # "b", "t1", "t2", etc.
            new_base = f"{tier_prefix}.{guid}"

            try:
                new_md_path = Path(dirpath) / f"{new_base}.md"
                md_path.rename(new_md_path)
            except Exception as e:
                logger.warning("undertaker: rename file failed for %s: %s", md_path, e)
                continue  # skip dir rename if file rename failed

            try:
                new_dir_path = Path(dirpath).parent / new_base
                Path(dirpath).rename(new_dir_path)
            except Exception as e:
                logger.warning("undertaker: rename dir failed for %s: %s", dirpath, e)

    return {
        "status": "success",
        "archived_count": archived_count,
        "archived_guids": sorted(archived_guids),
        "skipped": skipped,
    }


async def _undertaker(
    hive_name: str,
    query_yaml: str | None = None,
    query_name: str | None = None,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Archive bee tickets matching a query into the hive's /cemetery directory.

    Thin async wrapper that resolves repo_root, sets context, and delegates
    to _undertaker_core.

    Args:
        hive_name: Hive to operate on (required)
        query_yaml: YAML string for freeform query (mutually exclusive with query_name)
        query_name: Name of a registered query (mutually exclusive with query_yaml)
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict with status, archived_count, archived_guids, skipped
    """
    if resolved_root is not None:
        with repo_root_context(resolved_root):
            return _undertaker_core(hive_name, query_yaml=query_yaml, query_name=query_name)
    return _undertaker_core(hive_name, query_yaml=query_yaml, query_name=query_name)


class UndertakerScheduler:
    """Background scheduler that periodically runs the undertaker on configured hives.

    Spawns a daemon thread that sleeps in short increments and fires the
    undertaker for each hive whose interval has elapsed.
    """

    def __init__(self, bees_config: BeesConfig, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._schedules: list[dict[str, Any]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        for hive_name, hive_cfg in bees_config.hives.items():
            if hive_cfg.undertaker_schedule_seconds is None:
                continue
            self._schedules.append({
                "hive_name": hive_name,
                "interval": hive_cfg.undertaker_schedule_seconds,
                "query_yaml": hive_cfg.undertaker_schedule_query_yaml,
                "query_name": hive_cfg.undertaker_schedule_query_name,
                "log_path": hive_cfg.undertaker_schedule_log_path,
            })

    @property
    def active(self) -> bool:
        """True if there are hives with undertaker schedules configured."""
        return len(self._schedules) > 0

    def start(self) -> None:
        """Start the background scheduler thread."""
        if not self.active:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(
            "Undertaker scheduler started for %d hive(s)", len(self._schedules)
        )

    def stop(self) -> None:
        """Signal the scheduler to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("Undertaker scheduler stopped")

    def _run_loop(self) -> None:
        """Main loop: check schedules every second, fire when interval elapsed."""
        now = time.monotonic()
        for sched in self._schedules:
            sched["last_run"] = now
        while not self._stop_event.is_set():
            now = time.monotonic()
            for sched in self._schedules:
                if now - sched["last_run"] >= sched["interval"]:
                    sched["last_run"] = now
                    self._fire(sched)
            self._stop_event.wait(timeout=1.0)

    def _fire(self, sched: dict[str, Any]) -> None:
        """Execute one undertaker run for a scheduled hive."""
        hive_name = sched["hive_name"]
        with repo_root_context(self._repo_root):
            fresh_config = load_bees_config()
        if fresh_config is None:
            logger.warning(
                "undertaker-scheduler: hive=%s could not read config, skipping",
                hive_name,
            )
            return
        hive_config = fresh_config.hives.get(hive_name)
        if not hive_config or hive_config.undertaker_schedule_seconds is None:
            logger.info(
                "undertaker-scheduler: hive=%s no longer in config, skipping",
                hive_name,
            )
            return
        try:
            with repo_root_context(self._repo_root):
                result = _undertaker_core(
                    hive_name,
                    query_yaml=sched["query_yaml"],
                    query_name=sched["query_name"],
                )
            entry = (
                f"[{datetime.now(timezone.utc).isoformat()}] "
                f"[undertaker-scheduler] hive={hive_name} "
                f"query_name={sched.get('query_name') or ''} "
                f"query_yaml={sched.get('query_yaml') or ''} "
                f"status={result.get('status')} "
                f"archived={result.get('archived_count', 0)} "
                f"guids={result.get('archived_guids', [])} "
                f"skipped={result.get('skipped', [])}"
            )
            if result.get("status") == "error":
                entry += f" error={result.get('message', '')}"
            logger.info(entry)

            # Regenerate hive index after archival so index.md stays current
            if result.get("status") == "success":
                try:
                    with repo_root_context(self._repo_root):
                        generate_index(hive_name=hive_name)
                    logger.info(
                        "undertaker-scheduler: hive=%s index regenerated", hive_name
                    )
                except Exception as idx_err:
                    logger.warning(
                        "undertaker-scheduler: hive=%s index regeneration failed: %s",
                        hive_name,
                        idx_err,
                    )

            # Append to per-hive log file if configured
            log_path = sched.get("log_path")
            if log_path:
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(entry + "\n")
                except Exception as log_err:
                    logger.warning(
                        "undertaker-scheduler: could not write to log %s: %s",
                        log_path,
                        log_err,
                    )
        except Exception as e:
            logger.error(
                "undertaker-scheduler: unexpected error for hive=%s: %s",
                hive_name,
                e,
            )
