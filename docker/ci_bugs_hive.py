#!/usr/bin/env python3
"""Pick the bugs hive that CI files bugs into from a list of bees hives.

A failing CI test files a bug into the host's bugs hive for this repo. Its name differs between
machines, so it is never hardcoded: run_test.sh and file_bug.py both pick it from the hives bees
lists for the repo root (``bees list-hives`` run there, or the ``list_hives`` tool given that
``repo_root``), with the same rule.

bees lists more than the repo's own hives: also the hives of the less specific scopes above the
repo's own scope, and, for a queen repo, the hives of every scope. Each entry names the scope
pattern that owns it, so the rule goes by scope:

1. Only scopes whose pattern matches the repo root count, as bees matches them (wildcards anywhere
   in the pattern included), most specific first, in bees' own order: more path segments first,
   then an exact path before ``/*`` before ``/**``.
2. Within a scope, the candidates are the hive whose normalized name is ``bugs``, else every hive
   whose normalized name contains ``bugs`` (case-insensitive).
3. The answer comes from the most specific scope with a candidate, and only if that scope has
   exactly one. Several candidates there, or candidates in two equally specific scopes, is no
   answer; so is no candidate in any matching scope. Set BEES_BUGS_HIVE instead.

This script reads the JSON output of ``bees list-hives`` on stdin and prints the hive's normalized
name on stdout, with a one-line reason on stderr. It exits 0 when it found the hive, 1 otherwise.

Stdlib only: it runs on the host with plain python3, and file_bug.py imports it in the container.
ci_plan.py imports its scope matching on the host.

Usage:
    bees list-hives | python3 ci_bugs_hive.py --repo-root "$(pwd -P)"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import PurePosixPath

BUGS_HIVE_KEYWORD = "bugs"


def _entry(hive: object) -> tuple[str, str] | None:
    """Return a list-hives entry's (normalized name, owning scope), or None if it lacks either."""
    if not isinstance(hive, dict):
        return None
    name, scope = hive.get("normalized_name"), hive.get("scope")
    if isinstance(name, str) and name and isinstance(scope, str) and scope:
        return name, scope
    return None


# Scope matching and ranking. This script runs where bees is not importable, so the functions below
# copy bees' src/config.py (match_scope_pattern, compute_scope_specificity) unchanged in behavior.
# colonize-hive accepts a wildcard only as a terminal /* or /** (config.validate_scope_pattern), but
# bees matches whatever pattern a hand-written config holds, wildcards anywhere included (e.g.
# /x/bees*, /x/*/bees, /x/**/): so must this script.


def scope_pattern_regex(pattern: str) -> re.Pattern[str]:
    """The regex bees matches a repo root against for the scope ``pattern`` (config.match_scope_pattern)."""
    regex_parts = []
    i = 0
    while i < len(pattern):
        if i + 2 < len(pattern) and pattern[i] == "/" and pattern[i + 1] == "*" and pattern[i + 2] == "*":
            # /** : the directory itself or anything below it
            regex_parts.append("(/.*)?")
            i += 3
        elif i + 1 < len(pattern) and pattern[i] == "*" and pattern[i + 1] == "*":
            # ** anywhere else: anything, across segments
            regex_parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            # Terminal /* : one non-empty segment. Any other * : anything within a segment, even nothing.
            if i == len(pattern) - 1 and i > 0 and pattern[i - 1] == "/":
                regex_parts.append("[^/]+")
            else:
                regex_parts.append("[^/]*")
            i += 1
        elif pattern[i] == "/" and i == len(pattern) - 1:
            # Trailing slash: the path with or without it
            regex_parts.append("/?")
            i += 1
        else:
            regex_parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(regex_parts) + "$")


def scope_matches(pattern: str, repo_root: str) -> bool:
    """Whether bees counts the scope ``pattern`` for ``repo_root`` (config.match_scope_pattern)."""
    return bool(scope_pattern_regex(pattern).match(repo_root))


def compute_scope_specificity(pattern: str) -> tuple[int, int]:
    """Return bees' (segment count, wildcard tier) for a scope pattern (config.compute_scope_specificity).

    The tier is 2 for a terminal ``/**``, 1 for a terminal ``/*``, else 0. The count is the number of
    non-empty path segments left once that suffix (or trailing slashes) is cut off, wildcard segments
    included: ``/x/bees*`` has 2, ``/x/**/`` has 2 at tier 0.
    """
    if pattern.endswith("/**"):
        bare = pattern[:-3]
        tier = 2
    elif pattern.endswith("/*"):
        bare = pattern[:-2]
        tier = 1
    else:
        bare = pattern.rstrip("/")
        tier = 0
    segment_count = len([s for s in bare.split("/") if s])
    return (segment_count, tier)


def scope_specificity(pattern: str) -> tuple[int, int]:
    """Sort key, higher is more specific: (segments, -tier).

    bees ranks matching scopes by that key (config.find_matching_scope, config.find_all_matching_scopes).
    """
    segments, tier = compute_scope_specificity(pattern)
    return segments, -tier


def _candidates(names: set[str]) -> list[str]:
    """One scope's bugs hive candidates: the hive named ``bugs``, else every hive whose name contains it."""
    exact = [name for name in names if name.lower() == BUGS_HIVE_KEYWORD]
    return exact or [name for name in names if BUGS_HIVE_KEYWORD in name.lower()]


def choose_bugs_hive(hives: list, repo_root: str) -> tuple[str | None, str]:
    """Return (hive, reason): the normalized name of the bugs hive for ``repo_root``, or None and why there is none.

    ``hives`` is the ``hives`` list of a bees list-hives result for ``repo_root``: dicts with a
    ``normalized_name`` and the ``scope`` pattern that owns the hive. Entries without either are
    skipped. ``repo_root`` is the path the hives were listed for.
    """
    root = str(PurePosixPath(repo_root))  # as bees sees it: Path(repo_root) drops a trailing slash
    entries = [_entry(hive) for hive in hives]
    names_by_scope: dict[str, set[str]] = {}
    for name, scope in filter(None, entries):
        names_by_scope.setdefault(scope, set()).add(name)

    # Most specific first. A queen repo's list also holds scopes that do not match it: never used.
    matching = sorted(
        (scope for scope in names_by_scope if scope_matches(scope, root)), key=scope_specificity, reverse=True
    )
    for specificity in sorted({scope_specificity(scope) for scope in matching}, reverse=True):
        found = {
            scope: candidates
            for scope in sorted(scope for scope in matching if scope_specificity(scope) == specificity)
            if (candidates := sorted(_candidates(names_by_scope[scope])))
        }
        if len(found) > 1:
            listed = "; ".join(f"{scope}: {', '.join(candidates)}" for scope, candidates in found.items())
            return None, f"several equally specific scopes for {root} have bugs hives ({listed})"
        if found:
            [(scope, candidates)] = found.items()
            if len(candidates) > 1:
                return None, (
                    f"several hives in scope {scope} (the most specific scope for {root} with a bugs hive) "
                    f"have {BUGS_HIVE_KEYWORD!r} in their name: {', '.join(candidates)}"
                )
            [name] = candidates
            how = (
                f"the hive named {BUGS_HIVE_KEYWORD!r}"
                if name.lower() == BUGS_HIVE_KEYWORD
                else f"the only hive whose name contains {BUGS_HIVE_KEYWORD!r}"
            )
            return name, f"bugs hive {name}: {how} in scope {scope}, the most specific scope for {root} with one"

    if not matching:
        reason = f"no hive is listed in a scope that matches {root}"
    else:
        reason = f"no hive in the scopes for {root} ({', '.join(matching)}) has {BUGS_HIVE_KEYWORD!r} in its name"
    elsewhere = sorted(
        f"{name} (scope {scope})"
        for scope, names in names_by_scope.items()
        if scope not in matching
        for name in _candidates(names)
    )
    if elsewhere:
        reason += f"; bugs hives of other scopes, not used: {', '.join(elsewhere)}"
    skipped = entries.count(None)
    if skipped:
        reason += f"; skipped {skipped} entries without a normalized_name and a scope"
    return None, reason


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read 'bees list-hives' JSON on stdin and print the name of the bugs hive CI files bugs into."
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        help="The directory 'bees list-hives' ran in, symlinks resolved (bees picks the hives by it)",
    )
    args = parser.parse_args(argv)

    try:
        result = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        result = None
    hives = result.get("hives") if isinstance(result, dict) else None
    if not isinstance(hives, list):
        detail = f": {result['message']}" if isinstance(result, dict) and result.get("message") else ""
        print(f"no bugs hive: the input is not a bees list-hives result{detail}", file=sys.stderr)
        return 1

    hive, reason = choose_bugs_hive(hives, args.repo_root)
    print(reason, file=sys.stderr)
    if hive is None:
        return 1
    print(hive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
