"""Upgrade compatibility: this code reads and re-saves hives written by the released bees-md 0.8.4.

The corpus in tests/fixtures/compat_0_8_4/ was written by bees-md 0.8.4 and holds what 0.8.4
reads from it (expected.json). scripts/generate_compat_fixtures.py rebuilds it; see
docs/architecture/testing.md "Upgrade Compatibility Tests".

COMPAT: every ticket file reads exactly as 0.8.4 reads it, except for the intended changes
listed one by one in INTENDED_READ_CHANGES. ROUND TRIP: reading and saving a ticket with no
changes leaves its file byte-identical, except for the reasons in REWRITE_REASONS.
"""

import json
import re
import shutil
from dataclasses import asdict, fields
from pathlib import Path

import pytest
import yaml

from src import cache
from src.models import Ticket
from src.parser import parse_frontmatter
from src.reader import read_ticket
from src.writer import write_ticket_file
from tests.helpers import (
    COMPAT_084_ROOT,
    cli_success,
    compat_084_hive_of,
    compat_084_rels,
    load_compat_084,
    load_script,
    snapshot_diff,
    tree_snapshot,
)

GENERATOR = load_script(Path(__file__).resolve().parent.parent / "scripts" / "generate_compat_fixtures.py")

MANIFEST = load_compat_084("manifest")
EXPECTED = load_compat_084("expected")
ROLES = MANIFEST["roles"]
ROLE_OF = {ticket_id: role for role, ticket_id in ROLES.items()}

# Intended read changes since 0.8.4, by fixture role. Every other ticket file reads exactly as in 0.8.4.
B_PP8 = "b.pp8: body keeps leading/trailing whitespace that 0.8.4 stripped"
B_5YY = "b.5yy: '---' inside a frontmatter value no longer ends the frontmatter"
INTENDED_READ_CHANGES = {
    "tree_t1_b": {B_PP8},  # CRLF body ending in a line break
    "body_trailing_spaces": {B_PP8},
    "body_escapes_expanded_by_084": {B_PP8},  # ends in a tab, expanded from a literal \t by 0.8.4
    "body_yaml_like": {B_PP8},
    "body_file_bee": {B_PP8},
    "moved_bee": {B_PP8},  # move-bee does not rewrite the file
    "bug_crlf_file": {B_PP8},
    "bug_cross_hive_dep": {B_PP8},
    "idea_t1": {B_PP8},
    # 0.8.4 cut the value at '---' and read the rest of the frontmatter into the body
    "dash_ref_bee": {B_5YY},
    "dash_tag_bee": {B_5YY},
}
# 0.8.4 strips the body every time it saves a ticket, so these, saved again after create (a child
# or dependency added, a field updated), hold the stripped body on disk: they read as in 0.8.4.
BODY_STRIPPED_BY_084_SAVE = {
    "tree_bee", "tree_t1", "tree_t2", "blocker_bee", "blocked_bee", "dep_t1", "clone_source_bee",
    "archived_t1", "idea_bee", "plan_bee", "plan_t1", "plan_t2", "shared_bee",
}
# Built by 0.8.4 appends, not only from the create input
BODY_NOT_FROM_INPUT = {"appended_bee"}
ID_TO_REL = compat_084_rels()


def _role(ticket_id: str) -> str | None:
    return ROLE_OF.get(ticket_id)


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return {"datetime": value.isoformat()}
    return value


def _holds_dashes(value) -> bool:
    if isinstance(value, dict):
        return any(_holds_dashes(v) for v in value.values())
    if isinstance(value, list):
        return any(_holds_dashes(v) for v in value)
    return isinstance(value, str) and "---" in value


def _differences(old: dict, new: dict, body_key: str, frontmatter: dict) -> set[str]:
    """Name each difference between a 0.8.4 read and this code's read; any other by field."""
    if "error" in old:
        # 0.8.4 could not read it at all
        return {B_5YY} if _holds_dashes(frontmatter) else {"unexpected: 0.8.4 could not read it"}
    found = set()
    for key in old.keys() | new.keys():
        if old.get(key) == new.get(key):
            continue
        if _holds_dashes(frontmatter) and (old.get(key) is None or _holds_dashes(new.get(key)) or key == body_key):
            # 0.8.4 cut the frontmatter at the '---': it lost or cut the later fields and misread the body
            found.add(B_5YY)
        elif key == body_key and isinstance(new.get(key), str) and new[key].strip() == old.get(key):
            found.add(B_PP8)
        else:
            found.add(f"unexpected change in {key}")
    return found


def _expected_changes(ticket_id: str) -> set[str]:
    return INTENDED_READ_CHANGES.get(_role(ticket_id), set())


def _check_dash_ticket(ticket_id: str, values: dict, body: str) -> None:
    """A b.5yy ticket reads with every value given to 0.8.4, its own guid and its body."""
    given = MANIFEST["inputs"][ticket_id]
    refs = [{k: v for k, v in ref.items() if k != "resolved"} for ref in values.get("reference_materials") or []]
    assert refs == (given["reference_materials"] or [])
    assert (values["title"], values["status"]) == (given["title"], given["status"])
    assert (values.get("tags") or []) == (given["tags"] or [])
    assert re.fullmatch(r"[a-z0-9]{32}", values["guid"]) and values["guid"].startswith(ticket_id.split(".", 1)[1])
    assert body == _as_084_stored(given["body"])


def _as_084_stored(body: str) -> str:
    """The body 0.8.4 stored for an input: literal \\n and \\t expanded, then read with universal newlines."""
    body = body.replace("\\n", "\n").replace("\\t", "\t")
    return body.replace("\r\n", "\n").replace("\r", "\n")


# --- COMPAT ------------------------------------------------------------------------------


@pytest.mark.parametrize("rel", sorted(EXPECTED["parse"]))
def test_parse_matches_084(compat_084, rel):
    """parse_frontmatter of every ticket file, live or archived, matches 0.8.4's but for the listed changes."""
    old = EXPECTED["parse"][rel]
    frontmatter, body = parse_frontmatter(compat_084 / rel)
    new = {"body": body, **{f"fm.{k}": v for k, v in _jsonable(frontmatter).items()}}
    if "error" not in old:
        old = {"body": old["body"], **{f"fm.{k}": v for k, v in old["frontmatter"].items()}}

    assert _differences(old, new, "body", frontmatter) == _expected_changes(frontmatter["id"])
    if B_5YY in _expected_changes(frontmatter["id"]):
        _check_dash_ticket(frontmatter["id"], frontmatter, body)


@pytest.mark.parametrize("ticket_id", sorted(EXPECTED["show"]))
def test_show_ticket_matches_084(compat_084, cli_runner, ticket_id):
    """show-ticket of every live ticket matches 0.8.4's, resolved reference materials included."""
    new = cli_success(cli_runner, "show-ticket", "--ids", ticket_id)["tickets"][0]
    frontmatter = parse_frontmatter(compat_084 / ID_TO_REL[ticket_id])[0]

    assert _differences(EXPECTED["show"][ticket_id], new, "body", frontmatter) == _expected_changes(ticket_id)
    if B_5YY in _expected_changes(ticket_id):
        _check_dash_ticket(ticket_id, {**new, "status": new["ticket_status"]}, new["body"])


@pytest.mark.parametrize(
    "ticket_id",
    sorted(t for t, given in MANIFEST["inputs"].items() if given["body"] and _role(t) not in BODY_NOT_FROM_INPUT),
)
def test_body_reads_as_given_to_084(compat_084, ticket_id):
    """A body reads back as 0.8.4 stored it from the create input (escapes expanded, CRs as \\n), whitespace
    included, unless a later 0.8.4 save stripped it on disk."""
    body = parse_frontmatter(compat_084 / ID_TO_REL[ticket_id])[1]
    stored = _as_084_stored(MANIFEST["inputs"][ticket_id]["body"])

    assert body == (stored.strip() if _role(ticket_id) in BODY_STRIPPED_BY_084_SAVE else stored)


@pytest.mark.parametrize("command", ["list-hives", "get-types", "get-status-values", "list-named-queries"])
def test_config_reads_match_084(compat_084, cli_runner, command):
    """The 0.8.4 global config (repo scope, glob scope, global level, hive identity files) reads the same."""
    expected = json.dumps(EXPECTED["config"][command.replace("-", "_")]).replace(COMPAT_084_ROOT, str(compat_084))

    assert cli_success(cli_runner, command) == json.loads(expected)


@pytest.mark.parametrize("hive", sorted(EXPECTED["queries"]))
def test_freeform_query_matches_084(compat_084, cli_runner, hive):
    """A query lists the same tickets, plus the hive's b.5yy ticket that 0.8.4 silently left out."""
    new = cli_success(cli_runner, "execute-freeform-query", "--query-yaml", GENERATOR.query_yaml_for_hive(hive))
    old = EXPECTED["queries"][hive]
    unreadable_in_084 = {
        t for t, shown in EXPECTED["show"].items() if "error" in shown and compat_084_hive_of(ID_TO_REL[t]) == hive
    }

    assert set(new["ticket_ids"]) == set(old["ticket_ids"]) | unreadable_in_084


# --- PRIORITY (b.1zh) ---------------------------------------------------------------------
# 0.8.4 has no priority field: its tickets have no priority, and its priority:N tags stay tags.

# Live tickets carrying a priority:N tag, and those tags
PRIORITY_TAGGED = {
    t: tags
    for t, shown in EXPECTED["show"].items()
    if (tags := [tag for tag in shown.get("tags") or [] if re.fullmatch(r"priority:-?\d+", tag)])
}


def _query(cli_runner, *stage: str) -> set[str]:
    terms = ", ".join(f"'{term}'" for term in stage)
    return set(cli_success(cli_runner, "execute-freeform-query", "--query-yaml", f"stages:\n  - [{terms}]\n")["ticket_ids"])


def test_084_tickets_have_no_priority(compat_084, cli_runner):
    """No 0.8.4 ticket file holds a priority key, and show-ticket gives every live ticket priority null."""
    shown = cli_success(cli_runner, "show-ticket", "--ids", *EXPECTED["show"])

    assert (shown["not_found"], shown["errors"]) == ([], [])
    assert {t["ticket_id"]: t["priority"] for t in shown["tickets"]} == dict.fromkeys(EXPECTED["show"])
    assert not [rel for rel in EXPECTED["parse"] if "priority" in parse_frontmatter(compat_084 / rel)[0]]


def test_084_priority_tags_corpus():
    """The corpus holds old priority:N tags on more than one hive, so the tag tests below test something."""
    assert len({compat_084_hive_of(ID_TO_REL[t]) for t in PRIORITY_TAGGED}) > 1


@pytest.mark.parametrize("hive", sorted(EXPECTED["queries"]))
def test_priority_none_matches_every_084_ticket(compat_084, cli_runner, hive):
    """priority=none lists every ticket of each 0.8.4 hive, every tier, as a query without it does."""
    every = _query(cli_runner, f"hive={hive}")

    assert every and _query(cli_runner, f"hive={hive}", "priority=none") == every


@pytest.mark.parametrize(
    "term",
    ["priority=1", "priority=2", "priority!=1", "priority<100", "priority<=0", "priority>-100", "priority>=0"],
)
def test_numeric_priority_terms_match_no_084_ticket(compat_084, cli_runner, term):
    """No numeric priority term, priority!=N included, matches a 0.8.4 ticket, nor one with a priority:N tag."""
    assert _query(cli_runner, term) == set()


@pytest.mark.parametrize("ticket_id", sorted(PRIORITY_TAGGED))
def test_084_priority_tag_stays_a_tag(compat_084, cli_runner, ticket_id):
    """A 0.8.4 priority:N tag is a plain tag: shown and matched as a tag, never read as the priority field."""
    (shown,) = cli_success(cli_runner, "show-ticket", "--ids", ticket_id)["tickets"]
    (tag,) = PRIORITY_TAGGED[ticket_id]
    value = tag.split(":", 1)[1]

    assert (shown["priority"], shown["tags"]) == (None, EXPECTED["show"][ticket_id]["tags"])
    assert ticket_id in _query(cli_runner, f"tag~{tag}")
    assert ticket_id in _query(cli_runner, f"tag~{tag}", "priority=none")
    assert ticket_id not in _query(cli_runner, f"priority={value}") | _query(cli_runner, f"priority>={value}")


# --- ROUND TRIP --------------------------------------------------------------------------

# Why a ticket file may change when it is read and saved with no change. 0.8.4 makes the same
# changes (each save is checked against 0.8.4's own save in expected.json): none is a regression.
KEY_ORDER = (
    "key order: create-ticket writes the keys in its own order, and leaves out unset parent or "
    "reference_materials; every save writes them in Ticket field order, unset ones as null"
)
CR_TO_LF = "CR line endings: the file is read with universal newlines, so every \\r\\n or \\r is saved as \\n"
REWRITE_REASONS = {KEY_ORDER, CR_TO_LF}
# Keys every save writes, as null when unset
_ALWAYS_WRITTEN = {"parent", "reference_materials", "created_at", "status", "schema_version", "guid"}
_FIELD_ORDER = [f.name for f in fields(Ticket) if f.name != "body"]


def _rewrite_reasons(original: bytes) -> set[str]:
    reasons = {CR_TO_LF} if b"\r" in original else set()
    text = original.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    keys = list(yaml.safe_load(text[3 : text.find("\n---", 3)]))
    canonical = [k for k in _FIELD_ORDER if k in keys or k in _ALWAYS_WRITTEN]
    if keys != canonical:
        reasons.add(KEY_ORDER)
    return reasons


def _frontmatter_bytes(data: bytes) -> bytes:
    """The frontmatter, both delimiters included, of a file bees wrote."""
    return data[: data.find(b"\n---\n") + len(b"\n---\n")]


def _save_unchanged(path: Path) -> bytes:
    cache.clear()
    ticket_id = parse_frontmatter(path)[0]["id"]
    ticket = read_ticket(ticket_id, file_path=path)
    data = asdict(ticket)
    body = data.pop("body")
    write_ticket_file(ticket_id, ticket.type, data, body, file_path=path)
    return path.read_bytes()


@pytest.mark.parametrize("rel", sorted(EXPECTED["rewrite"]))
def test_save_unchanged_keeps_file(compat_084, rel):
    """Read and save with no change: byte-identical, or changed only for the listed reasons, as 0.8.4 did."""
    path = compat_084 / rel
    original = path.read_bytes()
    before_fm, before_body = parse_frontmatter(path)
    reasons = _rewrite_reasons(original)

    saved = _save_unchanged(path)

    if not reasons:
        assert saved == original
        return
    # No value changes: the file reads back the same, keys added as null aside
    after_fm, after_body = parse_frontmatter(path)
    assert after_body == before_body
    assert after_fm == {**dict.fromkeys(after_fm.keys() - before_fm.keys()), **before_fm}
    assert all(after_fm[k] is None for k in after_fm.keys() - before_fm.keys())
    # A second save changes nothing
    assert _save_unchanged(path) == saved
    # 0.8.4's own save wrote the same file; it stripped the body of the b.pp8 tickets (compare the
    # frontmatter only) and misread the b.5yy tickets (not comparable)
    changes = _expected_changes(before_fm["id"])
    if B_5YY in changes:
        return
    old_save = EXPECTED["rewrite"][rel]["bytes"]
    old_bytes = original if old_save is None else old_save.encode("utf-8")
    if B_PP8 in changes:
        assert _frontmatter_bytes(saved) == _frontmatter_bytes(old_bytes)
    else:
        assert saved == old_bytes


def test_every_rewrite_reason_occurs(compat_084):
    """Each listed rewrite reason is real: some corpus file has it, and some file has none."""
    per_file = [_rewrite_reasons((compat_084 / rel).read_bytes()) for rel in EXPECTED["rewrite"]]

    assert set().union(*per_file) == REWRITE_REASONS
    assert set() in per_file


@pytest.mark.parametrize("ticket_id", sorted(EXPECTED["show"]))
def test_update_with_same_title_saves_like_core(compat_084, cli_runner, ticket_id, tmp_path):
    """update-ticket setting a ticket's own title writes what a core no-change save writes, nothing else."""
    path = compat_084 / ID_TO_REL[ticket_id]
    copy = tmp_path / "core" / path.name
    copy.parent.mkdir()
    shutil.copyfile(path, copy)
    core_saved = _save_unchanged(copy)
    title = parse_frontmatter(path)[0]["title"]
    before = tree_snapshot(compat_084)

    cli_success(cli_runner, "update-ticket", "--ids", ticket_id, f"--title={title}")

    changed = {ID_TO_REL[ticket_id]} if core_saved != before[ID_TO_REL[ticket_id]] else set()
    assert snapshot_diff(before, tree_snapshot(compat_084)) == (set(), set(), changed)
    assert path.read_bytes() == core_saved
