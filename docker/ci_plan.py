#!/usr/bin/env python3
"""Read the CI test plan from this checkout, and find the hive /ci may record phase statuses through.

The CI containers run the test plan b.qi9 from this checkout's copy of the testplans hive,
docker/testplans (run_test.sh mounts it). /ci must read and update that same copy. The host's
registered hives are no guide to it: their testplans hive is often another copy (in a worktree,
usually the main checkout's), and on another machine docker/testplans may not be registered at all.
So:

- The plan, its phases in order with each epic's ID, title and status, is read from the files here.
- Phase statuses are written through bees (``bees update-ticket --hive``), and only into a hive whose
  path is this docker/testplans: matched by path, never by name. That hive must be one that bees,
  run from the repo root, resolves by name: of the listed hives in scopes that match the repo root,
  the most specific scope's definition of each name. Without one, the status hive is null: /ci then
  records nothing.

This script reads the JSON output of ``bees list-hives``, run from the current directory (the repo
root /ci runs bees from), on stdin. It prints on stdout:

    {"plan": "b.qi9", "testplans_path": "<this checkout>/docker/testplans",
     "phases": [{"phase": 1, "id": "t1...", "title": "Phase 1: ...", "status": "finished"}, ...],
     "status_hive": "<hive name>" or null, "status_hive_reason": "<why>"}

It exits 0 once it has read the plan (the status hive may still be null), 1 with the reason on
stderr when it cannot read the plan.

Stdlib only: it runs on the host with plain python3.

Usage:
    bees list-hives | python3 docker/ci_plan.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

from ci_bugs_hive import scope_matches, scope_specificity

PLAN_ID = "b.qi9"
# This checkout's copy of the testplans hive: the one run_test.sh mounts into the containers
TESTPLANS_PATH = Path(__file__).resolve().parent / "testplans"
FRONTMATTER_DELIMITER = "---"
_FIELD = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):(?:\s+(.*))?")
# A child ID names a directory below the plan's: never a path of its own
_TICKET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.]*")


class PlanError(Exception):
    """The plan cannot be read. The message says why."""


def _scalar(raw: str) -> str | None:
    """Decode a YAML scalar as bees writes it: plain, 'single quoted', "double quoted", or null."""
    if raw in ("", "null", "~"):
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw[1:-1]
    return raw


def read_frontmatter(path: Path) -> dict[str, object]:
    """Return the top-level fields of a ticket file's YAML frontmatter.

    Not a YAML parser (stdlib only): it reads what the plan's fields need, as bees writes them.
    That is ``key: value`` scalars, block lists of scalars (``key:`` then ``- item`` lines), and
    indented lines continuing the scalar above them (folded into it with a space).
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise PlanError(f"cannot read {path}: {exc}") from None
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        raise PlanError(f"{path} has no YAML frontmatter")

    raw: dict[str, str | list] = {}
    key = None
    for line in lines[1:]:
        # As in bees' parse_frontmatter, the closing delimiter is the first line that starts with
        # "---": an indented line of dashes belongs to a multi-line value above it
        if line.startswith(FRONTMATTER_DELIMITER):
            return {k: v if isinstance(v, list) else _scalar(v.strip()) for k, v in raw.items()}
        stripped = line.strip()
        if not stripped:
            continue
        if key is not None and isinstance(raw[key], list) and (stripped == "-" or stripped.startswith("- ")):
            raw[key].append(_scalar(stripped[1:].strip()))
        elif line[0].isspace() and key is not None and isinstance(raw[key], str):
            raw[key] += " " + stripped
        elif field := _FIELD.fullmatch(line):
            key = field.group(1)
            value = field.group(2) or ""
            raw[key] = value if value.strip() else []
        else:
            key = None  # a value this reader does not handle: skip it and what continues it
    raise PlanError(f"{path}: the YAML frontmatter is not closed by a {FRONTMATTER_DELIMITER} line")


def read_plan(testplans: Path) -> list[dict[str, object]]:
    """Return the plan's phases in order (1st child epic = Phase 1), each with its epic's ID, title and status."""
    plan_dir = testplans / PLAN_ID
    plan_file = plan_dir / f"{PLAN_ID}.md"
    if not plan_file.is_file():
        raise PlanError(f"test plan {PLAN_ID} not found in {testplans} (no {PLAN_ID}/{PLAN_ID}.md there)")
    children = read_frontmatter(plan_file).get("children")
    if not isinstance(children, list) or not children:
        raise PlanError(f"test plan {PLAN_ID} in {plan_file} lists no child epics")

    phases = []
    for number, epic_id in enumerate(children, start=1):
        if not isinstance(epic_id, str) or not _TICKET_ID.fullmatch(epic_id):
            raise PlanError(f"test plan {PLAN_ID} lists an invalid child epic ID: {epic_id!r}")
        epic_file = plan_dir / epic_id / f"{epic_id}.md"
        if not epic_file.is_file():
            raise PlanError(f"epic {epic_id} of test plan {PLAN_ID} not found: no {epic_file}")
        epic = read_frontmatter(epic_file)
        phases.append({"phase": number, "id": epic_id, "title": epic.get("title"), "status": epic.get("status")})
    return phases


def _resolved_hives(hives: list, repo_root: str) -> dict[str, set[str]]:
    """Map each hive name bees resolves for ``repo_root`` to its path(s), symlinks resolved.

    bees merges the hives of the scopes matching the repo root, the most specific scope's definition
    of a name winning (config.get_scoped_config). A queen repo's list also holds the hives of other
    scopes: bees does not resolve those names here. Two equally specific definitions of a name leave
    it with both paths: which one bees uses is not certain.
    """
    best: dict[str, tuple[tuple[int, int], set[str]]] = {}
    for hive in hives:
        if not isinstance(hive, dict):
            continue
        name, scope, path = hive.get("normalized_name"), hive.get("scope"), hive.get("path")
        if not all(isinstance(value, str) and value for value in (name, scope, path)):
            continue
        if not os.path.isabs(path) or not scope_matches(scope, repo_root):
            continue
        rank = scope_specificity(scope)
        if name not in best or rank > best[name][0]:
            best[name] = (rank, {os.path.realpath(path)})
        elif rank == best[name][0]:
            best[name][1].add(os.path.realpath(path))
    return {name: paths for name, (_, paths) in best.items()}


def find_status_hive(hives: list, repo_root: str, testplans: Path) -> tuple[str | None, str]:
    """Return (hive, reason): the hive bees resolves for ``repo_root`` to ``testplans``, or None and why.

    Matched by path, symlinks resolved, never by name.
    """
    root = str(PurePosixPath(repo_root))
    target = os.path.realpath(testplans)
    resolved = _resolved_hives(hives, root)
    names = sorted(name for name, paths in resolved.items() if paths == {target})
    if names:
        return names[0], f"hive {names[0]} is this checkout's copy: its path is {target}"

    reason = f"no hive that bees resolves for {root} has this checkout's {target} as its path"
    other_copies = sorted(
        f"{name} ({path})"
        for name, paths in resolved.items()
        for path in paths
        if path != target and os.path.isfile(os.path.join(path, PLAN_ID, f"{PLAN_ID}.md"))
    )
    if other_copies:
        reason += f"; hives holding another copy of {PLAN_ID}, which /ci leaves untouched: {', '.join(other_copies)}"
    ambiguous = sorted(name for name, paths in resolved.items() if target in paths and len(paths) > 1)
    if ambiguous:
        reason += f"; equally specific scopes give {', '.join(ambiguous)} different paths, one of them this copy"
    return None, reason


def _listed_hives(list_hives_output: str) -> tuple[list | None, str]:
    """Return the hives in ``bees list-hives`` JSON output, or None and why there are none."""
    try:
        result = json.loads(list_hives_output)
    except json.JSONDecodeError:
        result = None
    hives = result.get("hives") if isinstance(result, dict) else None
    if isinstance(hives, list):
        return hives, ""
    if isinstance(result, dict) and result.get("message"):
        return None, f"'bees list-hives' failed: {result['message']}"
    return None, "no 'bees list-hives' result on stdin"


def main() -> int:
    try:
        phases = read_plan(TESTPLANS_PATH)
    except PlanError as exc:
        print(f"cannot read the test plan: {exc}", file=sys.stderr)
        return 1

    hives, reason = _listed_hives(sys.stdin.read())
    status_hive = None
    if hives is not None:
        # The repo root bees picks the hives by when run from here (it resolves symlinks)
        status_hive, reason = find_status_hive(hives, str(Path.cwd().resolve()), TESTPLANS_PATH)

    print(
        json.dumps(
            {
                "plan": PLAN_ID,
                "testplans_path": str(TESTPLANS_PATH),
                "phases": phases,
                "status_hive": status_hive,
                "status_hive_reason": reason,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
