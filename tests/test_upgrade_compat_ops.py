"""Upgrade compatibility: operations on hives written by the released bees-md 0.8.4.

Each test runs one operation on a copy of the 0.8.4 corpus (tests/fixtures/compat_0_8_4/, see
tests/test_upgrade_compat.py) and compares tree snapshots taken before and after it: no ticket or
file may be lost, added or changed beyond what the operation is meant to do, and the global config
changes only where the operation changes it. Cases that hit a known bug are strict xfails naming the bug.
"""

import json
from pathlib import Path

import pytest

from src.config import load_bees_config
from src.id_utils import normalize_hive_name
from src.linter import Linter
from src.parser import parse_frontmatter
from tests.helpers import (
    COMPAT_084_HIVE_DIRS,
    cli_success,
    compat_084_rels,
    load_compat_084,
    snapshot_diff,
    tree_snapshot,
)

ROLES = load_compat_084("manifest")["roles"]
REL = compat_084_rels()
LIVE = sorted(load_compat_084("expected")["show"])
HIVE_DIRS = COMPAT_084_HIVE_DIRS


def _dir(ticket_id: str) -> str:
    return REL[ticket_id].rsplit("/", 1)[0]


def _under(snapshot: dict, prefix: str) -> set[str]:
    return {p for p in snapshot if p == prefix or p.startswith(prefix + "/")}


def _read(data: bytes, tmp_path: Path) -> tuple[dict, str]:
    path = tmp_path / "read" / "t.md"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return parse_frontmatter(path)


def _same_values(before: dict, after: dict) -> bool:
    """Equal frontmatter, keys a save adds as null aside."""
    return after == {**dict.fromkeys(after.keys() - before.keys()), **before}


class Corpus:
    """Snapshots of the corpus tree and the global config around one operation."""

    def __init__(self, root: Path, global_bees: Path):
        self.root = root
        self.config_path = global_bees / "config.json"
        self.before = tree_snapshot(root)
        self.config_before = self.config_path.read_text()

    def diff(self) -> tuple[set[str], set[str], set[str]]:
        self.after = tree_snapshot(self.root)
        return snapshot_diff(self.before, self.after)

    def config_changed(self) -> bool:
        return self.config_path.read_text() != self.config_before


@pytest.fixture
def corpus(compat_084, mock_global_bees_dir):
    return Corpus(compat_084, mock_global_bees_dir)


# --- update and append -------------------------------------------------------------------


@pytest.mark.parametrize("ticket_id", LIVE)
def test_update_adds_only_the_tag(corpus, cli_runner, tmp_path, ticket_id):
    """update-ticket --add-tags rewrites only that ticket, adding only the tag."""
    cli_success(cli_runner, "update-ticket", "--ids", ticket_id, "--add-tags", '["compat-op"]')

    rel = REL[ticket_id]
    assert corpus.diff() == (set(), set(), {rel})
    before_fm, before_body = _read(corpus.before[rel], tmp_path)
    after_fm, after_body = _read(corpus.after[rel], tmp_path)
    assert after_fm.pop("tags") == (before_fm.pop("tags", None) or []) + ["compat-op"]
    assert _same_values(before_fm, after_fm)
    assert after_body == before_body
    assert not corpus.config_changed()


@pytest.mark.parametrize("ticket_id", LIVE)
def test_append_extends_only_the_body(corpus, cli_runner, tmp_path, ticket_id):
    """append-ticket-body rewrites only that ticket, adding the chunk to the end of its body."""
    chunk = "Appended after the upgrade.\n"

    cli_success(cli_runner, "append-ticket-body", "--ticket-id", ticket_id, f"--chunk={chunk}")

    rel = REL[ticket_id]
    assert corpus.diff() == (set(), set(), {rel})
    before_fm, before_body = _read(corpus.before[rel], tmp_path)
    after_fm, after_body = _read(corpus.after[rel], tmp_path)
    assert after_body == before_body + chunk
    assert _same_values(before_fm, after_fm)


@pytest.mark.parametrize(
    "new_up_roles",
    [
        pytest.param(["dep_tree_bee"], id="same_hive"),
        pytest.param(["dep_tree_bee", "bug_plain"], id="cross_hive"),
    ],
)
def test_dependency_update_touches_both_ends(corpus, cli_runner, tmp_path, new_up_roles):
    """Replacing up_dependencies rewrites the ticket and only the tickets it links or unlinks, both ends."""
    blocked, blocker = ROLES["blocked_bee"], ROLES["blocker_bee"]
    new_up = [ROLES[r] for r in new_up_roles]

    cli_success(cli_runner, "update-ticket", "--ids", blocked, "--up-deps", json.dumps(new_up))

    assert corpus.diff() == (set(), set(), {REL[t] for t in (blocked, blocker, *new_up)})
    fm = {t: _read(corpus.after[REL[t]], tmp_path)[0] for t in (blocked, blocker, *new_up)}
    assert fm[blocked]["up_dependencies"] == new_up
    assert blocked not in (fm[blocker].get("down_dependencies") or [])
    assert all(blocked in fm[t]["down_dependencies"] for t in new_up)
    for ticket in (blocked, blocker, *new_up):
        before_fm, before_body = _read(corpus.before[REL[ticket]], tmp_path)
        after_fm, after_body = _read(corpus.after[REL[ticket]], tmp_path)
        for key in ("up_dependencies", "down_dependencies"):
            before_fm.pop(key, None)
            after_fm.pop(key, None)
        assert _same_values(before_fm, after_fm) and after_body == before_body


# --- move-bee ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "role,destination,force",
    [
        pytest.param("idea_plain", "features", False, id="bee_from_outer_hive"),
        pytest.param("idea_bee", "features", True, id="bee_with_child_from_outer_hive_forced"),
        pytest.param("plan_dep_bee", "bugs", False, id="bee_out_of_nested_hive"),
        pytest.param("tree_bee", "plans", False, id="every_tier_into_nested_hive"),
        pytest.param("moved_bee", "features", False, id="bee_moved_by_084_back"),
    ],
)
def test_move_bee_moves_the_tree_unchanged(corpus, cli_runner, role, destination, force):
    """The bee's whole directory moves byte for byte to the destination hive; nothing else changes."""
    bee = ROLES[role]
    src = _dir(bee)

    cli_success(cli_runner, "move-bee", "--ids", bee, "--hive", destination, *(["--force"] if force else []))

    added, removed, changed = corpus.diff()
    dest = f"{HIVE_DIRS[destination]}/{bee}"
    assert removed == _under(corpus.before, src)
    assert added == {dest + p[len(src):] for p in removed}
    assert all(corpus.after[dest + p[len(src):]] == corpus.before[p] for p in removed)
    assert changed == set()
    assert not corpus.config_changed()


def test_move_bee_refuses_hive_of_another_scope(corpus, cli_runner):
    """A bee of the glob-scope hive is not moved into the repo scope's hive (failed), and nothing changes."""
    bee = ROLES["shared_bee"]

    result = cli_success(cli_runner, "move-bee", "--ids", bee, "--hive", "features", "--force")

    assert (result["moved"], [f["id"] for f in result["failed"]]) == ([], [bee])
    assert corpus.diff() == (set(), set(), set())


# --- undertaker ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hive,query,roles",
    [
        pytest.param("features", "['id={tree_bee}']", ["tree_bee"], id="every_tier"),
        pytest.param("features", "['id={guid22_bee}']", ["guid22_bee"], id="22_char_guids"),
        pytest.param("ideas", "['type=bee']", None, id="outer_hive_of_nested_hive"),
        pytest.param("bugs", "['status=done']", ["bug_done"], id="first_cemetery_in_hive"),
    ],
)
def test_undertaker_archives_only_the_matched_trees(corpus, cli_runner, tmp_path, hive, query, roles):
    """Archived trees move into the cemetery byte for byte, renamed to {tier}.{guid}; the earlier
    cemetery, the nested hive and every other file stay as they are."""
    query = query.format(**ROLES)

    cli_success(cli_runner, "undertaker", "--hive", hive, "--query-yaml", f"stages:\n  - {query}\n")

    added, removed, changed = corpus.diff()
    hive_dir = HIVE_DIRS[hive]
    bees = [ROLES[r] for r in roles] if roles else [
        t for t in LIVE if _dir(t).rsplit("/", 1)[0] == hive_dir and t.startswith("b.")
    ]
    assert removed == set().union(*(_under(corpus.before, _dir(b)) for b in bees))
    assert changed == set()
    assert all(p.startswith(f"{hive_dir}/cemetery") for p in added)
    added_files = {p: corpus.after[p] for p in added if corpus.after[p] is not None}
    assert sorted(added_files.values()) == sorted(corpus.before[p] for p in removed if corpus.before[p] is not None)
    for path, data in added_files.items():
        fm = _read(data, tmp_path)[0]
        tier = "b" if fm["type"] == "bee" else fm["type"]
        assert Path(path).parent.name == Path(path).stem == f"{tier}.{fm['guid']}"
    assert not corpus.config_changed()


# --- delete --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,parent_role",
    [
        pytest.param("tree_t1", "tree_bee", id="epic_with_subtree"),
        pytest.param("blocker_bee", None, id="bee_others_depend_on"),
        pytest.param("idea_bee", None, id="bee_in_outer_hive_of_nested_hive"),
        pytest.param("plan_t2", "plan_t1", id="task_in_nested_hive"),
    ],
)
def test_delete_removes_only_the_subtree(corpus, cli_runner, tmp_path, role, parent_role):
    """Delete removes the ticket's directory; only its parent's children list changes.
    With delete_with_dependencies off (the default) dependents keep the now dangling ID."""
    ticket = ROLES[role]

    cli_success(cli_runner, "delete-ticket", "--ids", ticket)

    added, removed, changed = corpus.diff()
    assert (added, removed) == (set(), _under(corpus.before, _dir(ticket)))
    if parent_role is None:
        assert changed == set()
        return
    parent = REL[ROLES[parent_role]]
    assert changed == {parent}
    before_fm, before_body = _read(corpus.before[parent], tmp_path)
    after_fm, after_body = _read(corpus.after[parent], tmp_path)
    assert after_fm.get("children", []) == [c for c in before_fm["children"] if c != ticket]
    after_fm.pop("children", None)
    before_fm.pop("children")
    assert _same_values(before_fm, after_fm) and after_body == before_body


@pytest.mark.parametrize(
    "dependent_role",
    [
        pytest.param("blocked_bee", id="same_hive"),
        pytest.param("bug_cross_hive_dep", id="cross_hive"),
    ],
)
def test_delete_with_dependencies_cleans_dependents(corpus, cli_runner, tmp_path, dependent_role):
    """With delete_with_dependencies on, a dependent loses the deleted ID; no other ticket changes."""
    config = json.loads(corpus.config_path.read_text())
    corpus.config_path.write_text(json.dumps({**config, "delete_with_dependencies": True}))
    blocker = ROLES["blocker_bee"]
    dependents = {REL[ROLES[r]] for r in ("blocked_bee", "bug_cross_hive_dep")}
    dependent = REL[ROLES[dependent_role]]

    cli_success(cli_runner, "delete-ticket", "--ids", blocker)

    added, removed, changed = corpus.diff()
    assert (added, removed) == (set(), _under(corpus.before, _dir(blocker)))
    assert dependent in changed and changed <= dependents
    before_fm, before_body = _read(corpus.before[dependent], tmp_path)
    after_fm, after_body = _read(corpus.after[dependent], tmp_path)
    assert after_fm.pop("up_dependencies", []) == [d for d in before_fm.pop("up_dependencies") if d != blocker]
    assert _same_values(before_fm, after_fm) and after_body == before_body


# --- rename-hive ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "old,new,new_dir,flags",
    [
        pytest.param("features", "Feature Requests", "repo/feature_requests", [], id="folder_renamed"),
        pytest.param("plans", "Roadmap", "repo/Ideas/roadmap", [], id="nested_hive_folder_renamed"),
        pytest.param("bugs", "Defects", "repo/Bugs", ["--no-rename-folder"], id="folder_kept"),
    ],
)
def test_rename_hive_keeps_every_ticket(corpus, cli_runner, old, new, new_dir, flags):
    """Every ticket and index file keeps its bytes under the hive's new folder; only identity.json changes."""
    cli_success(cli_runner, "rename-hive", "--old-name", old, "--new-name", new, *flags)

    added, removed, changed = corpus.diff()
    old_dir = HIVE_DIRS[old]
    moved = {p: new_dir + p[len(old_dir):] for p in _under(corpus.before, old_dir)}
    if old_dir == new_dir:
        assert (added, removed) == (set(), set())
    else:
        assert (removed, added) == (set(moved), set(moved.values()))
    identity = f"{old_dir}/.hive/identity.json"
    assert changed == ({identity} if old_dir == new_dir else set())
    assert all(corpus.after[to] == corpus.before[frm] for frm, to in moved.items() if frm != identity)
    identity_after = json.loads(corpus.after[moved[identity]])
    assert identity_after["display_name"] == new
    # The config changes only by the hive's entry: its key, display name and path
    before, after = json.loads(corpus.config_before), json.loads(corpus.config_path.read_text())
    (repo_scope,) = [k for k in before["scopes"] if k.endswith("/repo")]
    entry = before["scopes"][repo_scope]["hives"].pop(old)
    before["scopes"][repo_scope]["hives"][normalize_hive_name(new)] = {
        **entry, "display_name": new, "path": str(corpus.root / new_dir)
    }
    assert after == before


def test_colonize_keeps_named_queries_and_other_scopes_hives(corpus, cli_runner):
    """Adding a hive to the repo scope keeps its named queries and leaves every other command working."""
    cli_success(cli_runner, "colonize-hive", "--name", "Extra", "--path", str(corpus.root / "repo" / "extra"))

    names = [q["name"] for q in cli_success(cli_runner, "list-named-queries")["queries"]]
    assert {"done_bees", "bees_with_children"} <= set(names)


def test_rename_hive_refuses_folder_holding_nested_hive(corpus, cli_runner):
    """Renaming the folder of the outer hive is refused (b.xvo) and changes nothing."""
    stdout, code = cli_runner(["rename-hive", "--old-name", "ideas", "--new-name", "Notions"])

    assert (code, json.loads(stdout)["error_type"]) == (1, "nested_hive")
    assert corpus.diff() == (set(), set(), set())
    assert not corpus.config_changed()


# --- sanitize and the linter ----------------------------------------------------------------

# What sanitize and the linter report on each 0.8.4 hive. None of it is auto-fixed, so no file changes.
EXPECTED_LINT = {
    "features": {
        ("guid22_bee", "invalid_guid_length"),
        ("guid22_t1", "invalid_guid_length"),
        # 0.8.4 create-ticket accepted a multi-line title, which the linter warns about
        ("title_48", "multiline_title"),
    },
    "bugs": {("bug_guid22", "invalid_guid_length")},
    "ideas": set(),
    "plans": set(),
    "shared_hive": set(),
}
ROLE_OF = {ticket_id: role for role, ticket_id in ROLES.items()}


def _lint_set(errors) -> set[tuple[str, str]]:
    """(role, error type) of each report."""
    return {(ROLE_OF.get(e["ticket_id"], e["ticket_id"]), e["error_type"]) for e in errors}


@pytest.mark.parametrize("hive", sorted(EXPECTED_LINT))
def test_sanitize_changes_no_file(corpus, cli_runner, hive):
    """sanitize-hive finds only the expected problems in each 0.8.4 hive and writes nothing,
    not even in the nested hive when sanitizing its outer hive (b.x6n, b.78s)."""
    stdout, _ = cli_runner(["sanitize-hive", "--hive", hive])
    result = json.loads(stdout)

    assert result["fixes_applied"] == []
    assert _lint_set(result["errors_remaining"]) == EXPECTED_LINT[hive]
    assert corpus.diff() == (set(), set(), set())
    assert not corpus.config_changed()


@pytest.mark.parametrize("hive", sorted(EXPECTED_LINT))
def test_linter_reports_without_writing(corpus, hive):
    """The linter without auto-fix reports the same problems and writes nothing."""
    config = load_bees_config()
    report = Linter(config.hives[hive].path, hive, config=config).run()

    errors = [{"ticket_id": e.ticket_id, "error_type": e.error_type} for e in report.errors]
    assert _lint_set(errors) == EXPECTED_LINT[hive]
    assert corpus.diff() == (set(), set(), set())


def test_sanitize_accepts_builtin_resolvers(corpus, cli_runner):
    """A reference material with a built-in resolver is valid, so sanitize does not report it."""
    result = json.loads(cli_runner(["sanitize-hive", "--hive", "plans"])[0])

    assert result["errors_remaining"] == []
