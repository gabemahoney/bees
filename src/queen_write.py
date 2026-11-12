"""Route write queens to a target's owning scope before calling write cores.

Both transports use the decorated async entry points. Configuration resolution
is narrowed for each call, so validation, relationships and configuration writes
use the same code as an ordinary caller in that scope.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path
from typing import Any

from .config import (
    ConfigLoadError,
    _parse_hives_data,
    canonicalize_scope_pattern,
    check_queen_elevation,
    check_schema_version,
    compute_scope_specificity,
    config_load_error_result,
    find_all_matching_scopes,
    load_global_config,
    match_scope_pattern,
    validate_scope_pattern,
)
from .id_utils import is_valid_ticket_id, normalize_hive_name
from .paths import build_ticket_path_map
from .repo_context import get_owning_scope, get_repo_root, owning_scope_context


class _AmbiguousScope(ValueError):
    """A queen's target or owning configuration view cannot be disambiguated."""


_WriteCore = Callable[..., Awaitable[dict[str, Any]]]
_WritePreflight = Callable[..., dict[str, Any] | None]
logger = logging.getLogger(__name__)


class _ScopeResolver:
    def __init__(self, root: Path, global_config: dict):
        self.root = root
        self.global_config = global_config
        self.scopes = global_config.get("scopes", {})
        # Matching names needs only the registry. Do not parse foreign settings
        # or probe any hive until an ID is actually missing from the local view.
        self.local = {pattern for pattern in self.scopes if match_scope_pattern(root, pattern)}
        self.local_hive_names = {
            name for pattern in self.local for name in self.scopes[pattern].get("hives", {})
        }
        self.views: dict[str, frozenset[str]] = {}
        self.ticket_scopes: dict[str, list[str]] = {}
        self.local_ticket_ids: set[str] = set()
        self.checked_ticket_ids: set[str] = set()

    def _select(self, candidates: list[str], target: str) -> str | None:
        if len(candidates) > 1:
            scopes = ", ".join(repr(pattern) for pattern in candidates)
            raise _AmbiguousScope(
                f"Ambiguous write target {target}: found in scopes {scopes}. "
                "Use repo_root / CLI cwd in the owning scope, or omit the hive name and use a unique ticket ID."
            )
        return candidates[0] if candidates else None

    def hive(self, name: str) -> str | None:
        normalized = normalize_hive_name(name)
        if normalized in self.local_hive_names:
            return None
        candidates = [
            pattern for pattern, data in self.scopes.items()
            if pattern not in self.local and normalized in data.get("hives", {})
        ]
        return self._select(candidates, f"hive '{normalized}'")

    def resolve_tickets(self, ticket_ids: list[str]) -> None:
        """Resolve a whole batch before writing, scanning only locally absent IDs."""
        needed = {tid for tid in ticket_ids if is_valid_ticket_id(tid)} - self.checked_ticket_ids
        if not needed:
            return
        local_hives = {}
        for _, config in find_all_matching_scopes(self.root, self.global_config):
            local_hives.update(config.hives)
        found = build_ticket_path_map(needed, hive_collection=list(local_hives.items()))
        self.local_ticket_ids.update(found)
        foreign_ids = needed - found.keys()
        if foreign_ids:
            for pattern, data in self.scopes.items():
                if pattern in self.local:
                    continue
                found_in_scope = set()
                for name, entry in data.get("hives", {}).items():
                    pending = foreign_ids - found_in_scope
                    if not pending:
                        break
                    hive = _parse_hives_data({name: entry})[name]
                    found_in_scope.update(_find_foreign_tickets(pending, pattern, name, hive))
                for ticket_id in found_in_scope:
                    self.ticket_scopes.setdefault(ticket_id, []).append(pattern)
        self.checked_ticket_ids.update(needed)

    def ticket(self, ticket_id: str) -> str | None:
        self.resolve_tickets([ticket_id])
        if ticket_id in self.local_ticket_ids:
            return None
        candidates = self.ticket_scopes.get(ticket_id, [])
        return self._select(candidates, f"ticket '{ticket_id}'")

    def view(self, owner: str | None) -> frozenset[str] | None:
        if owner is None:
            return None
        if owner not in self.views:
            self.views[owner] = _owner_view(owner, self.global_config)
        return self.views[owner]


def _find_foreign_tickets(ticket_ids: set[str], scope: str, name: str, hive) -> set[str]:
    """A missing or inaccessible foreign hive is unavailable, not a write failure."""
    path = Path(hive.path)
    try:
        if not path.is_dir():
            logger.warning("Skipping missing foreign hive %r in scope %r: %s", name, scope, path)
            return set()
        return set(build_ticket_path_map(ticket_ids, hive_collection=[(name, hive)]))
    except OSError as exc:
        logger.warning("Skipping unreadable foreign hive %r in scope %r: %s: %s", name, scope, path, exc)
        return set()


def _owner_view(owner: str, global_config: dict) -> frozenset[str]:
    """Find the scopes an owner inherits without inventing a wildcard's root."""
    try:
        validate_scope_pattern(owner)
        canonical = canonicalize_scope_pattern(owner)
        depth, tier = compute_scope_specificity(owner)
        prefix = canonical[:-3] if tier == 2 else canonical[:-2] if tier == 1 else canonical.rstrip("/")
        base = Path(prefix or "/")
        # An exact owner has a concrete root. A /* owner has the same less-
        # specific view at every direct child; /** may differ at its base and
        # below it. With terminal-only wildcards, these representatives exhaust
        # all less-specific cases. Exclude child-specific scopes: selecting one
        # would make that child the owner instead. Reject depth-dependent views
        # (e.g. /projects/* against /projects/app/**), rather than guess a root.
        roots = [base] if tier == 0 else [base / "__bees_scope__"]
        if tier == 2:
            roots.insert(0, base)
        visible = {owner}
        for pattern in global_config.get("scopes", {}):
            other_depth, other_tier = compute_scope_specificity(pattern)
            if tier and (other_depth, -other_tier) > (depth, -tier):
                continue
            if tier:
                validate_scope_pattern(pattern)
            matches = {match_scope_pattern(root, pattern) for root in roots}
            if len(matches) > 1:
                raise _AmbiguousScope(
                    f"Owning scope '{owner}' has a root-dependent view of '{pattern}'. "
                    "Use repo_root / CLI cwd at a concrete owning root to disambiguate."
                )
            if True in matches:
                visible.add(pattern)
        return frozenset(visible)
    except ValueError as exc:
        raise _AmbiguousScope(str(exc)) from exc


async def _call_in_scope(
    fn: _WriteCore, bound: inspect.BoundArguments, scope: str | None, visible_scopes: frozenset[str] | None,
) -> dict[str, Any]:
    if scope is None:
        return await fn(*bound.args, **bound.kwargs)
    assert visible_scopes is not None
    with owning_scope_context(scope, visible_scopes):
        return await fn(*bound.args, **bound.kwargs)


async def _run_groups(
    fn: _WriteCore, bound: inspect.BoundArguments, ticket_param: str, groups: dict[str | None, list[str]],
    resolver: _ScopeResolver, result_key: str,
) -> dict[str, Any]:
    """Run whole batches per scope, retaining the cores' list result shapes."""
    # Routing and schema errors are deterministic, so preflight every group's
    # view before any core runs. Later runtime failures must retain all results.
    views = {scope: resolver.view(scope) for scope in groups}
    if schema_error := check_schema_version():
        return schema_error
    combined = {"status": "success", result_key: [], "not_found": [], "failed": []}
    for scope, ids in groups.items():
        group_call = bound.signature.bind_partial()
        group_call.arguments.update(bound.arguments)
        group_call.arguments[ticket_param] = ids
        try:
            result = await _call_in_scope(fn, group_call, scope, views[scope])
        except ConfigLoadError as exc:
            result = config_load_error_result(exc)
        except Exception as exc:
            # This is the batch failure boundary, like the cores' per-ticket
            # loops: even an unexpected exception must not hide earlier writes.
            # A single group keeps its original exception behaviour.
            if len(groups) == 1:
                raise
            logger.exception("Write group failed in scope %r", scope)
            result = {"status": "error", "error_type": "write_error", "message": str(exc)}
        if len(groups) == 1:
            return result
        if result.get("status") != "success":
            reason = result.get("message") or result.get("error_type") or "Group write failed"
            combined["failed"].extend({"id": tid, "reason": reason} for tid in ids)
            continue
        for key in ("updated", "deleted", "moved", "skipped", "not_found", "failed"):
            if key in result:
                combined.setdefault(key, []).extend(result[key])
    return combined


async def _route_write(
    fn: _WriteCore, bound: inspect.BoundArguments, resolver: _ScopeResolver,
    hive_param: str | None, ticket_param: str | None, destination_param: str | None,
    batch_result_key: str | None,
) -> dict[str, Any]:
    arguments = bound.arguments
    hive = arguments.get(hive_param) if hive_param else None
    if hive:
        scope = resolver.hive(hive)
        return await _call_in_scope(fn, bound, scope, resolver.view(scope))
    destination = arguments.get(destination_param) if destination_param else None
    if destination is not None:
        scope = resolver.hive(destination)
        # The entire move/clone runs in the destination's view. Unseen sources
        # retain that owner's native not_found / cross-hive refusal behaviour.
        return await _call_in_scope(fn, bound, scope, resolver.view(scope))
    tickets = arguments.get(ticket_param) if ticket_param else None
    if isinstance(tickets, str):
        scope = resolver.ticket(tickets)
        return await _call_in_scope(fn, bound, scope, resolver.view(scope))
    if isinstance(tickets, list) and tickets and batch_result_key:
        resolver.resolve_tickets(tickets)
        groups: dict[str | None, list[str]] = {}
        for ticket_id in dict.fromkeys(tickets):
            scope = resolver.ticket(ticket_id)
            groups.setdefault(scope, []).append(ticket_id)
        return await _run_groups(fn, bound, ticket_param, groups, resolver, batch_result_key)
    return await fn(*bound.args, **bound.kwargs)


def queen_write_scope(
    *, hive_param: str | None = None, ticket_param: str | None = None, destination_param: str | None = None,
    hive_scope_only: bool = False, explicit_scope_param: str | None = None,
    batch_result_key: str | None = None,
    preflight: _WritePreflight | None = None,
) -> Callable[[_WriteCore], _WriteCore]:
    """Select scope using declarative target parameters on a shared write entry point.

    Missing targets stay on the original path, preserving each operation's errors
    and not_found behaviour. Batch IDs are resolved before any writes, so an
    ambiguity never produces a partially applied batch.
    """
    def decorate(fn: _WriteCore) -> _WriteCore:
        signature = inspect.signature(fn)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if get_owning_scope() is not None:
                return await fn(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = bound.arguments
            if hive_scope_only and arguments.get("scope") != "hive":
                return await fn(*args, **kwargs)
            # abandon_hive already supports an exact scope parameter.
            if explicit_scope_param and arguments.get(explicit_scope_param) is not None:
                return await fn(*args, **kwargs)
            root = arguments.get("resolved_root") or get_repo_root()
            global_config = load_global_config()
            if check_queen_elevation(root, global_config) != (True, True):
                return await fn(*args, **kwargs)
            if preflight and (error := preflight(**arguments)):
                return error

            tickets = arguments.get(ticket_param) if ticket_param else None
            if tickets == []:
                return await fn(*args, **kwargs)
            resolver = _ScopeResolver(root, global_config)
            try:
                return await _route_write(
                    fn, bound, resolver, hive_param, ticket_param, destination_param, batch_result_key,
                )
            except _AmbiguousScope as exc:
                return {"status": "error", "error_type": "config_conflict", "message": str(exc)}

        return wrapper

    return decorate
