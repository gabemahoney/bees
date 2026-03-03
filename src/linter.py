"""Linter module for ticket validation.

This module provides the main linter infrastructure for validating tickets,
including scanning tickets from the filesystem and running validation checks.
"""

import json
import logging
import re
import time
from collections.abc import Generator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src import cache
from src.config import BeesConfig, resolve_child_tiers_for_hive, resolve_status_values_for_hive
from src.constants import GUID_LENGTH, ID_CHARSET
from src.id_utils import generate_guid, is_ticket_id, is_valid_ticket_id
from src.linter_report import LinterReport, ValidationError
from src.models import Ticket
from src.paths import iter_ticket_files_deep
from src.reader import read_ticket
from src.writer import write_ticket_file

logger = logging.getLogger(__name__)

DISALLOWED_FIELDS = {"owner", "priority", "description", "created_by", "updated_at", "bees_version", "ticket_status"}


class TicketScanner:
    """Scanner to load and iterate over all tickets from the filesystem.

    Uses the ticket reader module to load tickets from markdown files
    in the hierarchical hive directory structure. Scans recursively
    and excludes special directories (eggs, evicted, .hive).
    """

    def __init__(self, tickets_dir: str = "tickets", hive_name: str = "default"):
        """Initialize ticket scanner.

        Args:
            tickets_dir: Path to tickets directory (default: 'tickets')
            hive_name: Name of hive to use as prefix for IDs (default: 'default')
        """
        self.tickets_dir = Path(tickets_dir)
        self.hive_name = hive_name

    def scan_all(self) -> Generator[Ticket, None, None]:
        """Scan and yield all tickets from the filesystem.

        Uses deep directory traversal via iter_ticket_files_deep — enters all
        directories except hidden ones (.hive/), evicted/, and /cemetery.
        This broader scan allows the linter to find misplaced and invalid tickets.

        Yields:
            Ticket objects (Bee, Task, or Subtask)

        Raises:
            FileNotFoundError: If tickets directory doesn't exist
        """
        for ticket, _ in self.scan_all_with_paths():
            yield ticket

    def scan_all_with_paths(self) -> Generator[tuple[Ticket, Path], None, None]:
        """Scan and yield all tickets paired with their file paths.

        Uses deep directory traversal via iter_ticket_files_deep — enters all
        directories except hidden ones (.hive/), evicted/, and /cemetery.

        Yields:
            Tuples of (Ticket, Path) for each ticket file found

        Raises:
            FileNotFoundError: If tickets directory doesn't exist
        """
        if not self.tickets_dir.exists():
            raise FileNotFoundError(f"Tickets directory not found: {self.tickets_dir}")

        for md_file in iter_ticket_files_deep(self.tickets_dir):
            try:
                ticket_id = md_file.stem
                ticket = read_ticket(ticket_id, file_path=md_file)
                yield ticket, md_file
            except Exception as e:
                logger.error(f"Error loading ticket {md_file}: {e}")
                continue


class Linter:
    """Main linter class for orchestrating ticket validation.

    Coordinates ticket scanning, validation checks, and error reporting.
    Validation rules are implemented as methods that can be extended by
    other tasks.
    """

    def __init__(
        self,
        tickets_dir: str = "tickets",
        hive_name: str = "default",
        config: BeesConfig | None = None,
        auto_fix: bool = False,
        all_scope_ticket_map: dict[str, "Ticket"] | None = None,
        auto_fix_dangling_refs: bool = False,
    ):
        """Initialize linter.

        Args:
            tickets_dir: Path to tickets directory (default: 'tickets')
            hive_name: Name of hive to use as prefix for IDs (default: 'default')
            config: BeesConfig object (optional)
            auto_fix: If True, attempt to automatically fix detected problems (default: False)
            all_scope_ticket_map: Map of all ticket IDs to Ticket objects across all hives
                in the current repo scope. None if any hive failed to load.
            auto_fix_dangling_refs: If True, automatically remove dangling dependency/parent
                references instead of reporting them as errors (default: False)
        """
        if auto_fix_dangling_refs and not auto_fix:
            raise ValueError("auto_fix_dangling_refs requires auto_fix=True")
        self.tickets_dir = tickets_dir
        self.hive_name = hive_name
        self.config = config
        self.auto_fix = auto_fix
        self.all_scope_ticket_map = all_scope_ticket_map
        self.auto_fix_dangling_refs = auto_fix_dangling_refs
        self.scanner = TicketScanner(tickets_dir, hive_name)

    def run(self, detect_only: bool = False) -> LinterReport:
        """Run linter validation on all tickets.

        Scans all tickets, runs validation checks, and collects errors
        into a structured report.

        Args:
            detect_only: If True, skip enforce_directory_structure to avoid any
                disk writes. Use this when you only want to detect problems
                without modifying the filesystem. (default: False)

        Returns:
            LinterReport containing all validation errors found
        """
        report = LinterReport()

        logger.info("Starting linter scan")

        # Load all tickets into a list for multiple passes (with paths for per-ticket validation)
        ticket_path_pairs = list(self.scanner.scan_all_with_paths())
        tickets = [t for t, _ in ticket_path_pairs]
        ticket_count = len(tickets)

        # Run per-ticket validation checks
        for ticket, file_path in ticket_path_pairs:
            self.validate_ticket(ticket, report, file_path)

        # Run cross-ticket validation checks
        self.validate_disallowed_fields(tickets, report)
        self.validate_tier_exists(tickets, report)
        self.validate_id_uniqueness(tickets, report)
        self.validate_parent_children_bidirectional(tickets, report)
        self.validate_dependencies_bidirectional(tickets, report)

        # Enforce directory structure (skipped in detect_only mode to avoid disk writes)
        if not detect_only:
            self.enforce_directory_structure(tickets, report)

        # Detect empty ticket dirs — runs in all modes; auto_fix controls whether dirs are removed
        self.detect_empty_ticket_dirs(report)

        # Run cycle detection
        cycle_errors = self.detect_cycles(tickets)
        for error in cycle_errors:
            report.errors.append(error)

        logger.info(
            f"Linter scan complete. Scanned {ticket_count} tickets, found {len(report.errors)} validation errors"
        )

        return report

    def validate_ticket(self, ticket: Ticket, report: LinterReport, file_path: Path | None = None) -> None:
        """Run validation checks on a single ticket.

        This is a stub method that will be extended by other tasks to
        add specific validation rules (ID format, uniqueness, bidirectional
        relationships, cycles, etc.).

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
            file_path: Path to the ticket file on disk (optional, used for path/ID consistency checks)
        """
        # Required fields and field types validation
        self.validate_required_fields(ticket, report)
        self.validate_field_types(ticket, report)

        # Structural constraints
        self.validate_bee_constraints(ticket, report)

        # ID format validation
        self.validate_id_format(ticket, report)

        # Egg field presence check for bee tickets
        self.validate_egg_field_presence(ticket, report)

        # Egg JSON-serializable validation
        self.validate_egg_json_serializable(ticket, report)

        # Field format validation
        self.validate_title_format(ticket, report)
        self.validate_schema_version(ticket, report)
        self.validate_created_at(ticket, report)

        # Field value validation
        self.validate_status_field(ticket, report)

        # GUID validation
        self.validate_guid(ticket, report)

        # Path/ID consistency validation (SR-7.3)
        if file_path is not None:
            self.validate_path_matches_id(ticket, report, file_path)

    def validate_required_fields(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that required fields are present and non-empty.

        Checks that id, type, and title fields exist and are non-empty strings.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        required_fields = ["id", "type", "title"]

        for field in required_fields:
            value = getattr(ticket, field, None)

            if value is None:
                report.add_error(
                    ticket_id=ticket.id if hasattr(ticket, "id") and ticket.id else "unknown",
                    error_type="missing_required_field",
                    message=f"Missing required field: '{field}'",
                    severity="error",
                )
            elif not isinstance(value, str):
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="invalid_field_type",
                    message=f"Field '{field}' must be string, got {type(value).__name__}",
                    severity="error",
                )
            elif not value.strip():
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="missing_required_field",
                    message=f"Required field '{field}' cannot be empty",
                    severity="error",
                )

    def validate_field_types(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that list fields are lists of strings and parent is string or None.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        # Validate list fields
        list_fields = ["tags", "up_dependencies", "down_dependencies", "children"]

        for field in list_fields:
            value = getattr(ticket, field, None)

            if value is not None:
                if not isinstance(value, list):
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="invalid_field_type",
                        message=f"Field '{field}' must be list, got {type(value).__name__}",
                        severity="error",
                    )
                else:
                    # Check all items are strings
                    for i, item in enumerate(value):
                        if not isinstance(item, str):
                            report.add_error(
                                ticket_id=ticket.id,
                                error_type="invalid_field_type",
                                message=f"Field '{field}' must contain only strings, "
                                f"found {type(item).__name__} at index {i}",
                                severity="error",
                            )

        # Validate parent field
        if ticket.parent is not None and not isinstance(ticket.parent, str):
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_field_type",
                message=f"Field 'parent' must be string or None, got {type(ticket.parent).__name__}",
                severity="error",
            )

    def validate_bee_constraints(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that bees do not have parent field set.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        if ticket.type == "bee" and ticket.parent is not None:
            report.add_error(
                ticket_id=ticket.id,
                error_type="bee_has_parent",
                message=f"Bee ticket '{ticket.id}' must not have parent field set (found parent='{ticket.parent}')",
                severity="error",
            )

    def validate_egg_field_presence(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that bee tickets have egg field present in frontmatter.

        The egg field must be PRESENT in bee ticket frontmatter. A null/None value is valid,
        but a completely missing egg key is an error.

        Child tier tickets (t1, t2, t3, etc.) are not checked for egg field.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        # Only check bee tickets
        if ticket.type != "bee":
            return

        if "egg" not in getattr(ticket, "_raw_keys", frozenset()):
            report.add_error(
                ticket_id=ticket.id,
                error_type="missing_egg_field",
                message=f"Bee ticket '{ticket.id}' must have 'egg' field in frontmatter",
                severity="error",
            )

    def validate_id_format(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that ticket ID matches the required format.

        Checks if ticket ID matches the type-prefixed format (b.XXX, t1.XXXX, t2.XXXXX, etc.).

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        if not is_valid_ticket_id(ticket.id):
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_id",
                message=(
                    f"Ticket ID '{ticket.id}' does not match required type-prefixed format "
                    f"(b.XXX, t1.XXXX, t2.XXXXX, etc.)"
                ),
                severity="error",
            )

    def validate_title_format(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that ticket title does not contain newlines.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        if "\n" in ticket.title or "\r" in ticket.title:
            report.add_error(
                ticket_id=ticket.id,
                error_type="multiline_title",
                message="Title must not contain newlines",
                severity="warning",
            )

    def validate_schema_version(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that schema_version field matches version format (x.y or x.y.z).

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        schema_version = getattr(ticket, "schema_version", None)
        if (
            schema_version is None
            or not isinstance(schema_version, str)
            or not re.match(r"^\d+\.\d+(\.\d+)?$", schema_version)
        ):
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_schema_version",
                message="schema_version must be valid format (x.y or x.y.z)",
                severity="error",
            )

    def validate_created_at(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that created_at field is present and in valid ISO 8601 format.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        from datetime import datetime

        created_at = getattr(ticket, "created_at", None)
        if created_at is None:
            report.add_error(
                ticket_id=ticket.id,
                error_type="missing_date",
                message="created_at field is missing",
                severity="warning",
            )
        elif isinstance(created_at, datetime):
            return  # Already a valid datetime object
        elif isinstance(created_at, str):
            try:
                datetime.fromisoformat(created_at)
            except ValueError:
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="invalid_date_format",
                    message="created_at must be valid ISO 8601 format",
                    severity="warning",
                )
        else:
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_date_format",
                message="created_at must be valid ISO 8601 format",
                severity="warning",
            )

    def validate_status_field(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate status field value against configured status_values.

        Checks ticket.status against the resolved status_values from config.
        If status_values is configured, only values in that list are valid.
        If status_values is None (freeform), any string is valid.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        # Skip if status is None (missing status handled elsewhere or optional)
        if ticket.status is None:
            return

        # Validate type
        if not isinstance(ticket.status, str):
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_field_type",
                message="Field 'status' must be string",
                severity="error",
            )
            return

        # Check against configured status_values if config exists
        if self.config and self.hive_name:
            status_values = resolve_status_values_for_hive(self.hive_name, self.config)

            # If status_values is configured (not None), validate against it
            if status_values is not None:
                if ticket.status not in status_values:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="invalid_status",
                        message=(
                            f"Field 'status' has value '{ticket.status}'"
                            f" which is not in configured status_values: {status_values}"
                        ),
                        severity="error",
                    )

    def validate_guid(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate the guid field on a ticket.

        Checks:
        1. guid must be present (not None)
        2. guid length must equal GUID_LENGTH
        3. All characters in guid must be in ID_CHARSET
        4. guid must start with the ticket's short_id

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        if ticket.guid is None:
            if self.auto_fix:
                short_id = ticket.id.split(".", 1)[1]
                guid = generate_guid(short_id)
                ticket.guid = guid
                self._save_modified_tickets({ticket.id: ticket}, {ticket.id})
                report.add_fix(ticket_id=ticket.id, fix_type="add_guid", description=f"Generated guid {guid}")
                return
            report.add_error(
                ticket_id=ticket.id,
                error_type="missing_guid",
                message=f"Ticket '{ticket.id}' is missing required 'guid' field",
                severity="error",
            )
            return

        if len(ticket.guid) != GUID_LENGTH:
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_guid_length",
                message=f"Ticket '{ticket.id}' guid length is {len(ticket.guid)}, expected {GUID_LENGTH}",
                severity="error",
            )
            return

        invalid_chars = [c for c in ticket.guid if c not in ID_CHARSET]
        if invalid_chars:
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_guid_charset",
                message=f"Ticket '{ticket.id}' guid contains invalid characters: {invalid_chars}",
                severity="error",
            )
            return

        short_id = ticket.id.split(".", 1)[1].replace(".", "")
        if not ticket.guid.startswith(short_id):
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_guid_prefix",
                message=(
                    f"Ticket '{ticket.id}' guid must start with short_id"
                    f" '{short_id}', got '{ticket.guid[:len(short_id)]}'"
                ),
                severity="error",
            )

    def validate_path_matches_id(self, ticket: Ticket, report: LinterReport, file_path: Path) -> None:
        """Validate that the ticket's file path is consistent with its ID (SR-7.3).

        Checks that both the containing directory name and the filename stem
        match the ticket's frontmatter 'id' field.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
            file_path: Path to the ticket file on disk
        """
        dir_name = file_path.parent.name
        file_stem = file_path.stem

        mismatches = []
        if dir_name != ticket.id:
            mismatches.append(f"directory name '{dir_name}' does not match ticket id '{ticket.id}'")
        if file_stem != ticket.id:
            mismatches.append(f"filename stem '{file_stem}' does not match ticket id '{ticket.id}'")

        if mismatches:
            report.add_error(
                ticket_id=ticket.id,
                error_type="path_id_mismatch",
                message=f"Path/ID mismatch for '{file_path}': {'; '.join(mismatches)}",
                severity="error",
            )

    def validate_egg_json_serializable(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that egg field is JSON-serializable.

        Only applies to bee tickets. A null egg value is valid.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        # Only check bee tickets
        if ticket.type != "bee":
            return

        # Null/None egg is valid
        if ticket.egg is None:
            return

        # Try to serialize egg to JSON
        try:
            json.dumps(ticket.egg)
        except TypeError:
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_field_type",
                message="egg field must be JSON-serializable",
                severity="error",
            )

    def validate_disallowed_fields(self, tickets: list[Ticket], report: LinterReport) -> None:
        """Validate that tickets do not contain disallowed fields in frontmatter.

        Checks raw frontmatter keys (stashed on ticket._raw_keys by the reader)
        for presence of deprecated or disallowed fields.
        Each disallowed field found generates a separate error.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        for ticket in tickets:
            for key in getattr(ticket, '_raw_keys', frozenset()):
                if key in DISALLOWED_FIELDS:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="disallowed_field",
                        message=f"Ticket '{ticket.id}' contains disallowed field '{key}'",
                        severity="error",
                    )

    def _get_expected_parent_type(self, ticket_type: str, child_tiers: dict[str, Any]) -> str | None:
        """Get expected parent type for a given ticket type from child_tiers config.

        Args:
            ticket_type: Type of the ticket (e.g., 'bee', 't1', 't2', 't3')
            child_tiers: Dictionary of tier keys to ChildTierConfig objects

        Returns:
            Expected parent type string, or None if ticket_type is 'bee' or invalid
        """
        # Bees have no parent
        if ticket_type == "bee":
            return None

        # Bees-only system: empty child_tiers dict means only bees exist
        if not child_tiers:
            # Any non-bee type in bees-only system is invalid (handled by validate_tier_exists)
            return None

        # Extract tier number from type (e.g., "t2" -> 2)
        if not ticket_type.startswith("t"):
            return None

        try:
            tier_num = int(ticket_type[1:])
        except (ValueError, IndexError):
            return None

        # t1 always has bee as parent
        if tier_num == 1:
            return "bee"

        # t2 and higher have previous tier as parent (e.g., t2 expects t1, t3 expects t2)
        expected_parent = f"t{tier_num - 1}"

        # Verify expected parent exists in config
        if expected_parent not in child_tiers:
            return None

        return expected_parent

    def _get_expected_child_type(self, ticket_type: str, child_tiers: dict[str, Any]) -> str | None:
        """Get expected child type for a given ticket type from child_tiers config.

        Args:
            ticket_type: Type of the ticket (e.g., 'bee', 't1', 't2', 't3')
            child_tiers: Dictionary of tier keys to ChildTierConfig objects

        Returns:
            Expected child type string, or None if ticket has no valid children
        """
        # Bees-only system: empty child_tiers dict means only bees exist
        if not child_tiers:
            return None

        # Bees have t1 as children
        if ticket_type == "bee":
            return "t1" if "t1" in child_tiers else None

        # Extract tier number from type (e.g., "t2" -> 2)
        if not ticket_type.startswith("t"):
            return None

        try:
            tier_num = int(ticket_type[1:])
        except (ValueError, IndexError):
            return None

        # Next tier is child type (e.g., t1 expects t2, t2 expects t3)
        expected_child = f"t{tier_num + 1}"

        # Verify expected child exists in config
        if expected_child not in child_tiers:
            return None

        return expected_child

    def validate_parent_field(
        self,
        ticket: Ticket,
        report: LinterReport,
        ticket_map: dict[str, Ticket],
        modified_tickets: set | None = None,
    ) -> None:
        """Validate parent field format and existence.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
            ticket_map: Map of ticket IDs to Ticket objects
            modified_tickets: Optional set to accumulate IDs of tickets modified by auto-fix
        """
        # Skip if ticket is a bee (bees have no parent)
        if ticket.type == "bee":
            return

        # Skip if ticket has no parent field
        if not ticket.parent:
            return

        parent_id = ticket.parent

        # Validate parent ID format
        if not is_valid_ticket_id(parent_id):
            report.add_error(
                ticket_id=ticket.id,
                error_type="invalid_parent_id",
                message=f"Ticket '{ticket.id}' has invalid parent ID format: '{parent_id}'",
                severity="error",
            )
            return

        # Check for dangling parent reference across all hives in scope
        if self.all_scope_ticket_map is not None and parent_id not in self.all_scope_ticket_map:
            if self.auto_fix_dangling_refs and modified_tickets is not None:
                ticket.parent = None
                modified_tickets.add(ticket.id)
                report.add_fix(
                    ticket_id=ticket.id,
                    fix_type="clear_dangling_parent",
                    description=f"Cleared dangling parent reference '{parent_id}' from ticket '{ticket.id}'",
                )
            else:
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="dangling_parent",
                    message=(
                        f"Ticket '{ticket.id}' references non-existent parent '{parent_id}'"
                        " (not found in any hive)"
                    ),
                    severity="error",
                )
            return

        # Check parent exists in ticket_map (only when all-scope map unavailable;
        # when it is available, cross-hive parents are already validated above)
        if self.all_scope_ticket_map is None and parent_id not in ticket_map:
            report.add_error(
                ticket_id=ticket.id,
                error_type="orphaned_ticket",
                message=f"Ticket '{ticket.id}' references non-existent parent: '{parent_id}'",
                severity="error",
            )

    def validate_children_field(self, ticket: Ticket, report: LinterReport, ticket_map: dict[str, Ticket]) -> None:
        """Validate children field format and types.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
            ticket_map: Map of ticket IDs to Ticket objects
        """
        # Load config to get child_tiers
        from src.config import load_bees_config

        config = load_bees_config()

        if not config or self.hive_name not in config.hives:
            return

        child_tiers = resolve_child_tiers_for_hive(self.hive_name, config)
        if not child_tiers:
            return

        # Get expected child type for this ticket
        expected_child_type = self._get_expected_child_type(ticket.type, child_tiers)

        for child_id in (ticket.children or []):
            # Validate child ID format
            if not is_valid_ticket_id(child_id):
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="invalid_child_id",
                    message=f"Ticket '{ticket.id}' has invalid child ID format: '{child_id}'",
                    severity="error",
                )
                continue

            # If child exists in ticket_map, validate child type
            child_ticket = ticket_map.get(child_id)
            if child_ticket and expected_child_type:
                if child_ticket.type != expected_child_type:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="invalid_child_type",
                        message=(
                            f"Ticket '{ticket.id}' (type {ticket.type}) has child '{child_id}' "
                            f"with type {child_ticket.type}, expected {expected_child_type}"
                        ),
                        severity="error",
                    )

    def validate_up_dependencies_field(
        self,
        ticket: Ticket,
        report: LinterReport,
        ticket_map: dict[str, Ticket],
        modified_tickets: set | None = None,
    ) -> None:
        """Validate up_dependencies field format and cross-type consistency.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
            ticket_map: Map of ticket IDs to Ticket objects
            modified_tickets: Optional set to accumulate IDs of tickets modified by auto-fix
        """
        for upstream_id in list(ticket.up_dependencies):
            # Validate upstream ID format
            if not is_valid_ticket_id(upstream_id):
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="invalid_dependency_id",
                    message=f"Ticket '{ticket.id}' has invalid up_dependencies ID format: '{upstream_id}'",
                    severity="error",
                )
                continue

            # Check for dangling reference across all hives in scope
            if self.all_scope_ticket_map is not None and upstream_id not in self.all_scope_ticket_map:
                if self.auto_fix_dangling_refs and modified_tickets is not None:
                    ticket.up_dependencies.remove(upstream_id)
                    modified_tickets.add(ticket.id)
                    report.add_fix(
                        ticket_id=ticket.id,
                        fix_type="remove_dangling_dependency",
                        description=f"Removed dangling up_dependency '{upstream_id}' from ticket '{ticket.id}'",
                    )
                else:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="dangling_dependency",
                        message=f"Ticket '{ticket.id}' up_dependencies references non-existent ticket '{upstream_id}'",
                        severity="error",
                    )
                continue

            # If upstream exists, validate type consistency
            upstream_ticket = ticket_map.get(upstream_id)
            if upstream_ticket and upstream_ticket.type != ticket.type:
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="cross_type_dependency",
                    message=(
                        f"Ticket '{ticket.id}' (type {ticket.type}) has upstream dependency "
                        f"'{upstream_id}' with type {upstream_ticket.type}, types must match"
                    ),
                    severity="error",
                )

    def validate_down_dependencies_field(
        self,
        ticket: Ticket,
        report: LinterReport,
        ticket_map: dict[str, Ticket],
        modified_tickets: set | None = None,
    ) -> None:
        """Validate down_dependencies field format and cross-type consistency.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
            ticket_map: Map of ticket IDs to Ticket objects
            modified_tickets: Optional set to accumulate IDs of tickets modified by auto-fix
        """
        for downstream_id in list(ticket.down_dependencies):
            # Validate downstream ID format
            if not is_valid_ticket_id(downstream_id):
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="invalid_dependency_id",
                    message=f"Ticket '{ticket.id}' has invalid down_dependencies ID format: '{downstream_id}'",
                    severity="error",
                )
                continue

            # Check for dangling reference across all hives in scope
            if self.all_scope_ticket_map is not None and downstream_id not in self.all_scope_ticket_map:
                if self.auto_fix_dangling_refs and modified_tickets is not None:
                    ticket.down_dependencies.remove(downstream_id)
                    modified_tickets.add(ticket.id)
                    report.add_fix(
                        ticket_id=ticket.id,
                        fix_type="remove_dangling_dependency",
                        description=f"Removed dangling down_dependency '{downstream_id}' from ticket '{ticket.id}'",
                    )
                else:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="dangling_dependency",
                        message=(
                            f"Ticket '{ticket.id}' down_dependencies references"
                            f" non-existent ticket '{downstream_id}'"
                        ),
                        severity="error",
                    )
                continue

            # If downstream exists, validate type consistency
            downstream_ticket = ticket_map.get(downstream_id)
            if downstream_ticket and downstream_ticket.type != ticket.type:
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="cross_type_dependency",
                    message=(
                        f"Ticket '{ticket.id}' (type {ticket.type}) has downstream dependency "
                        f"'{downstream_id}' with type {downstream_ticket.type}, types must match"
                    ),
                    severity="error",
                )

    def validate_tier_exists(self, tickets: list[Ticket], report: LinterReport) -> None:
        """Validate that all ticket types are defined in child_tiers config.

        Checks each ticket's type against valid tier types defined in config.
        The 'bee' type is always valid (immutable base type).

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        # Load config to get valid tier types
        from src.config import load_bees_config

        config = load_bees_config()

        # Build set of valid types
        # - "bee" is always valid (immutable base type)
        # - Configured tier types (t1, t2, t3, etc.) from child_tiers
        valid_types = {"bee"}

        if config and self.hive_name in config.hives:
            child_tiers = resolve_child_tiers_for_hive(self.hive_name, config)
            if child_tiers:
                valid_types.update(child_tiers.keys())

        # Check each ticket's type
        for ticket in tickets:
            if ticket.type not in valid_types:
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="unknown_tier",
                    message=f"Ticket {ticket.id} has type '{ticket.type}' which is not defined in child_tiers",
                    severity="error",
                )

    def validate_id_uniqueness(self, tickets: list[Ticket], report: LinterReport) -> None:
        """Validate that all ticket IDs are unique (case-insensitive comparison).

        Scans all tickets and detects duplicate IDs across all ticket types.
        IDs are compared case-insensitively per SR-7.2.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        seen_ids = {}

        for ticket in tickets:
            ticket_id = ticket.id.lower()
            if ticket_id in seen_ids:
                # Duplicate found
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="duplicate_id",
                    message=f"Duplicate ticket ID '{ticket.id}' found (also in {seen_ids[ticket_id]})",
                    severity="error",
                )
            else:
                seen_ids[ticket_id] = ticket.type

    def validate_parent_children_bidirectional(self, tickets: list[Ticket], report: LinterReport) -> None:
        """Validate parent/children relationships with asymmetric policy.

        For each ticket with a parent field, verifies the parent ticket lists
        this ticket in its children field (child→parent direction enforced).

        Parent→child direction is NOT enforced: parents may list children that
        don't list them back (asymmetric policy per SR-6.2).

        When auto_fix is enabled, attempts to fix orphaned child→parent relationships.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        # Create a lookup map for quick ticket access by ID
        ticket_map = {ticket.id: ticket for ticket in tickets}
        modified_tickets = set()

        for ticket in tickets:
            # Validate parent field format and existence
            self.validate_parent_field(ticket, report, ticket_map, modified_tickets)

            # Validate children field format and types
            self.validate_children_field(ticket, report, ticket_map)

            # Check if ticket has a parent
            if ticket.parent:
                parent_id = ticket.parent
                parent_ticket = ticket_map.get(parent_id)

                if not parent_ticket:
                    # Parent ticket doesn't exist (handled by validate_parent_field)
                    continue

                # Verify parent lists this ticket in its children
                if ticket.id not in (parent_ticket.children or []):
                    if self.auto_fix:
                        # Auto-fix: Add this ticket to parent's children
                        if parent_ticket.children is None:
                            parent_ticket.children = []
                        parent_ticket.children.append(ticket.id)
                        modified_tickets.add(parent_id)
                        report.add_fix(
                            ticket_id=parent_id,
                            fix_type="add_child",
                            description=f"Added '{ticket.id}' to children of '{parent_id}'",
                        )
                    else:
                        report.add_error(
                            ticket_id=ticket.id,
                            error_type="orphaned_ticket",
                            message=f"Ticket '{ticket.id}' lists '{parent_id}' as parent, "
                            f"but '{parent_id}' does not list '{ticket.id}' in its children",
                            severity="error",
                        )

        # Validate tier hierarchy (parent type matches config expectations)
        # Load config to get child_tiers
        from src.config import load_bees_config

        config = load_bees_config()

        if config and self.hive_name in config.hives:
            child_tiers = resolve_child_tiers_for_hive(self.hive_name, config)
            if child_tiers:
                for ticket in tickets:
                    if ticket.parent:
                        parent_ticket = ticket_map.get(ticket.parent)
                        if not parent_ticket:
                            # Parent doesn't exist (handled by other validators)
                            continue

                        # Get expected parent type for this child's type
                        expected_parent_type = self._get_expected_parent_type(ticket.type, child_tiers)

                        # Check if parent type matches expected
                        if expected_parent_type is not None and parent_ticket.type != expected_parent_type:
                            report.add_error(
                                ticket_id=ticket.id,
                                error_type="invalid_tier_parent",
                                message=(
                                    f"Ticket {ticket.id} (type {ticket.type}) has invalid parent type "
                                    f"{parent_ticket.type}, expected {expected_parent_type}"
                                ),
                                severity="error",
                            )

        # Write modified tickets back to filesystem
        if self.auto_fix and modified_tickets:
            self._save_modified_tickets(ticket_map, modified_tickets)

    def validate_dependencies_bidirectional(self, tickets: list[Ticket], report: LinterReport) -> None:
        """Validate bidirectional consistency of dependency relationships.

        For each ticket with up_dependencies, verifies each upstream ticket
        lists this ticket in its down_dependencies. For each ticket with
        down_dependencies, verifies each downstream ticket lists this ticket
        in its up_dependencies.

        When auto_fix is enabled, attempts to fix orphaned dependency relationships.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        # Create a lookup map for quick ticket access by ID
        ticket_map = {ticket.id: ticket for ticket in tickets}
        modified_tickets = set()

        for ticket in tickets:
            # Validate dependency field formats and cross-type consistency
            self.validate_up_dependencies_field(ticket, report, ticket_map, modified_tickets)
            self.validate_down_dependencies_field(ticket, report, ticket_map, modified_tickets)
            # Check up_dependencies (this ticket depends on upstream tickets)
            for upstream_id in ticket.up_dependencies:
                upstream_ticket = ticket_map.get(upstream_id)

                if not upstream_ticket:
                    # Upstream ticket doesn't exist (handled by other validators)
                    continue

                # Verify upstream ticket lists this ticket in down_dependencies
                if ticket.id not in upstream_ticket.down_dependencies:
                    if self.auto_fix:
                        # Auto-fix: Add this ticket to upstream's down_dependencies
                        upstream_ticket.down_dependencies.append(ticket.id)
                        modified_tickets.add(upstream_id)
                        report.add_fix(
                            ticket_id=upstream_id,
                            fix_type="add_down_dependency",
                            description=f"Added '{ticket.id}' to down_dependencies of '{upstream_id}'",
                        )
                    else:
                        report.add_error(
                            ticket_id=ticket.id,
                            error_type="orphaned_dependency",
                            message=f"Ticket '{ticket.id}' lists '{upstream_id}' in up_dependencies, "
                            f"but '{upstream_id}' does not list '{ticket.id}' in its down_dependencies",
                            severity="error",
                        )

            # Check down_dependencies (downstream tickets depend on this ticket)
            for downstream_id in ticket.down_dependencies:
                downstream_ticket = ticket_map.get(downstream_id)

                if not downstream_ticket:
                    # Downstream ticket doesn't exist (handled by other validators)
                    continue

                # Verify downstream ticket lists this ticket in up_dependencies
                if ticket.id not in downstream_ticket.up_dependencies:
                    if self.auto_fix:
                        # Auto-fix: Add this ticket to downstream's up_dependencies
                        downstream_ticket.up_dependencies.append(ticket.id)
                        modified_tickets.add(downstream_id)
                        report.add_fix(
                            ticket_id=downstream_id,
                            fix_type="add_up_dependency",
                            description=f"Added '{ticket.id}' to up_dependencies of '{downstream_id}'",
                        )
                    else:
                        report.add_error(
                            ticket_id=ticket.id,
                            error_type="missing_backlink",
                            message=f"Ticket '{ticket.id}' lists '{downstream_id}' in down_dependencies, "
                            f"but '{downstream_id}' does not list '{ticket.id}' in its up_dependencies",
                            severity="error",
                        )

        # Write modified tickets back to filesystem
        if self.auto_fix and modified_tickets:
            self._save_modified_tickets(ticket_map, modified_tickets)

    def detect_empty_ticket_dirs(self, report: LinterReport) -> None:
        """Detect and optionally remove ticket directories that contain no .md file.

        A ticket directory can be left without a corresponding ticket file when
        generate_child_tier_id() claims a directory via mkdir but the subsequent
        write_ticket_file() call fails. These orphaned directories permanently block
        that ticket ID from future use.

        Directories newer than 10 minutes are skipped to avoid racing in-flight
        ticket creation.

        In auto-fix mode, orphaned directories are removed via dir_path.rmdir().
        In report-only mode, each orphaned directory is added as a LinterError.

        Args:
            report: LinterReport to collect errors and fixes into
        """
        tickets_dir = Path(self.tickets_dir)
        if not tickets_dir.exists():
            return

        cutoff = time.time() - 600  # 10 minutes

        for dir_path in tickets_dir.rglob("*"):
            if not dir_path.is_dir():
                continue

            dir_name = dir_path.name
            if not is_ticket_id(dir_name):
                continue

            # Check if any .md file exists in the directory
            if any(dir_path.glob("*.md")):
                continue

            # Skip recently created directories (in-flight ticket creation)
            try:
                mtime = dir_path.stat().st_mtime
            except OSError:
                continue

            if mtime >= cutoff:
                continue

            # Directory is old and has no ticket file — act on it
            if self.auto_fix:
                try:
                    dir_path.rmdir()
                    logger.info(f"Removed empty ticket directory: {dir_path}")
                    report.add_fix(
                        ticket_id=dir_name,
                        fix_type="remove_empty_dir",
                        description=f"Removed empty ticket directory with no .md file: {dir_path}",
                    )
                except OSError as e:
                    logger.error(f"Failed to remove empty ticket directory {dir_path}: {e}")
            else:
                report.add_error(
                    ticket_id=dir_name,
                    error_type="empty_ticket_dir",
                    message=f"Directory '{dir_path}' matches a ticket ID pattern but contains no .md file",
                    severity="error",
                )

    def enforce_directory_structure(self, tickets: list[Ticket], report: LinterReport) -> None:
        """Enforce hierarchical directory structure based on parent relationships.

        For each ticket with a parent, verifies the ticket's directory is located under
        the parent's directory. If not, automatically moves the ticket's directory (and
        all its children) to the correct location using shutil.move().

        For bees (tickets with no parent), verifies the directory is at hive root level.

        This is a core enforcement rule that always auto-moves misplaced tickets.
        Frontmatter is the source of truth; filesystem structure is derived from it.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect fixes and errors into
        """
        import shutil
        from pathlib import Path

        from .config import load_bees_config
        from .paths import find_ticket_file

        # Create a lookup map for quick ticket access by ID
        ticket_map = {ticket.id: ticket for ticket in tickets}

        # Load config to get hive paths
        config = load_bees_config()
        if not config or not config.hives:
            logger.warning("No hives configured, skipping directory structure enforcement")
            return

        for ticket in tickets:
            try:
                # Find which hive this ticket belongs to by looking for its file
                # Use deep=True to find misplaced tickets in non-standard directories
                ticket_hive = None
                ticket_path = None
                for hive_name, _hive_config in config.hives.items():
                    hive_path = Path(_hive_config.path)
                    found = find_ticket_file(hive_path, ticket.id, deep=True)
                    if found:
                        ticket_path = found
                        ticket_hive = hive_name
                        break

                if not ticket_path or not ticket_hive:
                    logger.warning(f"Could not find file for ticket {ticket.id}, skipping directory enforcement")
                    continue

                # Get current directory of this ticket
                logger.debug(f"Ticket {ticket.id}: ticket_path={ticket_path}")
                current_dir = ticket_path.parent
                logger.debug(f"Ticket {ticket.id}: current_dir (ticket_path.parent)={current_dir}")
                hive_path = Path(config.hives[ticket_hive].path)

                # Determine expected directory location
                if ticket.parent:
                    # Child ticket - should be under parent's directory
                    parent_ticket = ticket_map.get(ticket.parent)
                    if not parent_ticket:
                        # Parent doesn't exist - skip enforcement
                        continue

                    # Find parent's path (also deep search since parent may also be misplaced)
                    parent_path = find_ticket_file(hive_path, ticket.parent, deep=True)
                    if not parent_path:
                        # Parent file not found - skip enforcement
                        continue
                    expected_parent_dir = parent_path.parent
                    expected_dir = expected_parent_dir / ticket.id

                    # Check if ticket is in the correct location (use samefile to handle symlinks)
                    needs_move = False
                    try:
                        # Use samefile to handle symlinks correctly
                        if not current_dir.samefile(expected_dir):
                            needs_move = True
                    except (FileNotFoundError, ValueError, OSError):
                        # If paths don't exist or can't be compared, compare as strings
                        if current_dir != expected_dir:
                            needs_move = True

                    if needs_move:
                        # Move ticket directory to correct location
                        logger.info(
                            f"Moving ticket {ticket.id} from {current_dir} to {expected_dir} "
                            f"(parent enforcement for parent {ticket.parent})"
                        )

                        # Ensure expected parent directory exists
                        expected_parent_dir.mkdir(parents=True, exist_ok=True)

                        # If expected_dir already exists, remove it first to avoid nesting
                        if expected_dir.exists():
                            shutil.rmtree(expected_dir)

                        # Move the ticket's directory (and all children) to correct location
                        shutil.move(str(current_dir), str(expected_dir))
                        cache.evict(ticket.id)

                        report.add_fix(
                            ticket_id=ticket.id,
                            fix_type="move_directory",
                            description=f"Moved ticket directory to {expected_dir} (under parent {ticket.parent})",
                        )

                else:
                    # Bee (no parent) - should be at hive root level
                    expected_dir = hive_path / ticket.id

                    # Check if bee is at hive root (use samefile to handle symlinks)
                    logger.debug(f"Bee {ticket.id}: current_dir={current_dir}, expected_dir={expected_dir}")
                    needs_move = False
                    try:
                        # Use samefile to handle symlinks correctly
                        if not current_dir.samefile(expected_dir):
                            needs_move = True
                    except (FileNotFoundError, ValueError, OSError):
                        # If paths don't exist or can't be compared, compare as strings
                        if current_dir != expected_dir:
                            needs_move = True

                    if needs_move:
                        logger.info(f"Moving bee {ticket.id} from {current_dir} to {expected_dir} (hive root)")

                        # If expected_dir already exists, remove it first to avoid nesting
                        if expected_dir.exists():
                            shutil.rmtree(expected_dir)

                        # Move the bee's directory to hive root
                        shutil.move(str(current_dir), str(expected_dir))
                        cache.evict(ticket.id)

                        report.add_fix(
                            ticket_id=ticket.id,
                            fix_type="move_directory",
                            description=f"Moved bee directory to hive root at {expected_dir}",
                        )

            except Exception as e:
                logger.error(f"Error enforcing directory structure for ticket {ticket.id}: {e}")
                report.add_error(
                    ticket_id=ticket.id,
                    error_type="directory_enforcement_failed",
                    message=f"Failed to enforce directory structure: {e}",
                    severity="error",
                )

    def detect_cycles(self, tickets: list[Ticket]) -> list[ValidationError]:
        """Detect cycles in both blocking and hierarchical dependency relationships.

        Uses depth-first search (DFS) with path tracking to detect cycles in:
        1. Blocking dependencies (up_dependencies/down_dependencies)
        2. Hierarchical relationships (parent/children)

        Args:
            tickets: List of all tickets to check for cycles

        Returns:
            List of ValidationError objects for each cycle found, with cycle paths
        """
        errors = []
        ticket_map = {ticket.id: ticket for ticket in tickets}

        # Track visited nodes globally to avoid redundant cycle detection
        visited_blocking = set()
        visited_hierarchical = set()

        # Detect cycles in blocking dependencies
        for ticket in tickets:
            if ticket.id not in visited_blocking:
                cycle_path = self._detect_cycle_dfs(
                    ticket_id=ticket.id,
                    ticket_map=ticket_map,
                    visited=visited_blocking,
                    path=[],
                    path_set=set(),
                    get_neighbors=lambda t: t.up_dependencies,
                    relationship_type="blocking dependency",
                )
                if cycle_path:
                    cycle_str = " -> ".join(cycle_path)
                    errors.append(
                        ValidationError(
                            ticket_id=cycle_path[0],
                            error_type="dependency_cycle",
                            message=f"Cycle detected in blocking dependencies: {cycle_str}",
                            severity="error",
                        )
                    )

        # Detect cycles in hierarchical relationships (parent/children)
        for ticket in tickets:
            if ticket.id not in visited_hierarchical:
                cycle_path = self._detect_cycle_dfs(
                    ticket_id=ticket.id,
                    ticket_map=ticket_map,
                    visited=visited_hierarchical,
                    path=[],
                    path_set=set(),
                    get_neighbors=lambda t: [t.parent] if t.parent else [],
                    relationship_type="parent/child",
                )
                if cycle_path:
                    cycle_str = " -> ".join(cycle_path)
                    errors.append(
                        ValidationError(
                            ticket_id=cycle_path[0],
                            error_type="hierarchy_cycle",
                            message=f"Cycle detected in parent/child hierarchy: {cycle_str}",
                            severity="error",
                        )
                    )

        return errors

    def _detect_cycle_dfs(
        self,
        ticket_id: str,
        ticket_map: dict[str, Ticket],
        visited: set[str],
        path: list[str],
        path_set: set[str],
        get_neighbors,
        relationship_type: str,
    ) -> list[str] | None:
        """DFS helper to detect cycles in a specific relationship type.

        Args:
            ticket_id: Current ticket ID being explored
            ticket_map: Map of ticket IDs to Ticket objects
            visited: Set of globally visited nodes (to avoid redundant work)
            path: Current path from root to current node
            path_set: Set representation of path for O(1) cycle detection
            get_neighbors: Function to extract neighbor IDs from a ticket
            relationship_type: Type of relationship being checked (for error messages)

        Returns:
            List of ticket IDs representing the cycle path if cycle found, None otherwise
        """
        # Check if we've found a cycle
        if ticket_id in path_set:
            # Extract the cycle portion of the path
            cycle_start_idx = path.index(ticket_id)
            cycle = path[cycle_start_idx:] + [ticket_id]
            return cycle

        # Check if ticket exists
        ticket = ticket_map.get(ticket_id)
        if not ticket:
            # Missing ticket (handled by other validators)
            return None

        # Mark as visited globally
        visited.add(ticket_id)

        # Add to current path
        path.append(ticket_id)
        path_set.add(ticket_id)

        # Explore neighbors
        neighbors = get_neighbors(ticket)
        for neighbor_id in neighbors:
            if neighbor_id not in visited or neighbor_id in path_set:
                # Visit unvisited nodes or nodes in current path (potential cycle)
                cycle = self._detect_cycle_dfs(
                    ticket_id=neighbor_id,
                    ticket_map=ticket_map,
                    visited=visited,
                    path=path[:],
                    path_set=path_set.copy(),
                    get_neighbors=get_neighbors,
                    relationship_type=relationship_type,
                )
                if cycle:
                    return cycle

        # Remove from current path when backtracking
        path_set.discard(ticket_id)

        return None

    def _save_modified_tickets(self, ticket_map: dict[str, Ticket], modified_ids: set[str]) -> None:
        """Save modified tickets back to filesystem.

        Args:
            ticket_map: Map of ticket IDs to Ticket objects
            modified_ids: Set of ticket IDs that were modified during auto-fix
        """
        for ticket_id in modified_ids:
            ticket = ticket_map[ticket_id]

            frontmatter_data = asdict(ticket)
            frontmatter_data.pop("description", None)

            # Write ticket back to file
            try:
                write_ticket_file(
                    ticket_id=ticket.id,
                    ticket_type=ticket.type,
                    frontmatter_data=frontmatter_data,
                    body=ticket.description or "",
                    hive_name=self.hive_name,
                )
                cache.evict(ticket_id)
                logger.info(f"Saved modified ticket {ticket_id}")
            except Exception as e:
                logger.error(f"Failed to save modified ticket {ticket_id}: {e}")
