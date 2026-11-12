"""b.11s routing across multiple owners, batch preflight, and request isolation.

Public MCP functions and CLI main exercise real files in three scopes. The
single-owner operations and hive-management regressions live in sibling files.
"""

import asyncio
import json
import os
import stat
from types import SimpleNamespace

import pytest

from src import mcp_server
from src.config import load_bees_config, load_global_config, save_global_config
from src.paths import compute_ticket_path
from src.reader import read_ticket
from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config, write_queen_repos_config
from tests.helpers import snapshot_diff, tree_snapshot, write_ticket_file


@pytest.fixture
def routing_env(tmp_path, mock_global_bees_dir, monkeypatch):
    """A queen's local hive and two foreign scopes with distinct settings."""
    queen, owner_a, owner_b = (tmp_path / name for name in ("queen", "owner_a", "owner_b"))
    local, alpha, beta = queen / "local", owner_a / "alpha", owner_b / "beta"
    scopes = {}
    for root, hive, status in (
        (queen, local, "local_only"),
        (owner_a, alpha, "alpha_only"),
        (owner_b, beta, "beta_only"),
    ):
        hive.mkdir(parents=True)
        scopes[str(root)] = {
            "hives": {hive.name: {"path": str(hive), "display_name": hive.name.title()}},
            "status_values": [status, "done"],
            "child_tiers": {},
        }
    write_multi_scope_config(mock_global_bees_dir, scopes)
    write_queen_repos_config(mock_global_bees_dir, [(str(queen), True)])
    write_ticket_file(alpha, "b.aaa", title="Alpha ticket", status="alpha_only")
    write_ticket_file(beta, "b.bbb", title="Beta ticket", status="beta_only")
    write_ticket_file(local, "b.qqq", title="Local ticket", status="local_only")
    monkeypatch.chdir(queen)
    with repo_root_context(queen):
        yield SimpleNamespace(
            root=tmp_path, queen=queen, owner_a=owner_a, owner_b=owner_b,
            local=local, alpha=alpha, beta=beta,
        )


@pytest.fixture(params=["mcp", "cli"])
def routing_surface(request, routing_env, cli_runner, mock_mcp_context, monkeypatch):
    """Invoke a public operation at the queen, or at an owner for a control."""
    async def mcp_call(operation, *, root=None, **kwargs):
        root = root or routing_env.queen
        return await getattr(mcp_server, operation)(
            ctx=mock_mcp_context(root), repo_root=str(root), **kwargs,
        )

    def call(operation, *, root=None, **kwargs):
        if request.param == "mcp":
            return asyncio.run(mcp_call(operation, root=root, **kwargs))
        argv = ["clone" if operation == "clone_bee" else operation.replace("_", "-")]
        for key, value in kwargs.items():
            if key in ("ticket_ids", "bee_ids"):
                argv += ["--ids", *([value] if isinstance(value, str) else value)]
            else:
                argv += ["--" + key.replace("_", "-"), json.dumps(value) if isinstance(value, list) else value]
        with monkeypatch.context() as patch:
            patch.chdir(root or routing_env.queen)
            stdout, exit_code = cli_runner(argv)
        result = json.loads(stdout)
        assert exit_code == (0 if result["status"] == "success" else 1), result
        return result

    return SimpleNamespace(call=call, mcp_call=mcp_call, via=request.param)


def _duplicate_ticket(env):
    for hive in (env.alpha, env.beta):
        write_ticket_file(hive, "b.ccc", title="Duplicate ID", status="done")


def _stored(hive, ticket_id):
    return read_ticket(ticket_id, file_path=compute_ticket_path(ticket_id, hive))


def _assert_conflict(result, env):
    assert result["status"] == "error", result
    assert result["error_type"] == "config_conflict", result
    assert str(env.owner_a) in result["message"], result
    assert str(env.owner_b) in result["message"], result


def test_duplicate_foreign_ticket_id_refuses_single_update(routing_env, routing_surface):
    env = routing_env
    _duplicate_ticket(env)
    before = tree_snapshot(env.root)

    result = routing_surface.call("update_ticket", ticket_ids="b.ccc", status="done", add_tags=["changed"])

    assert tree_snapshot(env.root) == before
    _assert_conflict(result, env)


@pytest.mark.parametrize("operation,result_key", [
    pytest.param("update_ticket", "updated", id="update"),
    pytest.param("delete_ticket", "deleted", id="delete"),
])
@pytest.mark.parametrize("include_local", [False, True], ids=["foreign_owners", "mixed_local_foreign"])
def test_batch_routes_tickets_to_each_owner(
    routing_env, routing_surface, operation, result_key, include_local,
):
    env = routing_env
    targets = [(env.alpha, "b.aaa"), (env.beta, "b.bbb")]
    if include_local:
        # Local first: the foreign group's override must not affect the local group.
        targets.insert(0, (env.local, "b.qqq"))
    local_before = tree_snapshot(env.local)
    kwargs = {"status": "done", "add_tags": ["routed"]} if operation == "update_ticket" else {}

    result = routing_surface.call(operation, ticket_ids=[tid for _, tid in targets], **kwargs)

    assert result["status"] == "success", result
    assert sorted(result[result_key]) == sorted(tid for _, tid in targets)
    assert result["not_found"] == []
    assert result["failed"] == []
    for hive, ticket_id in targets:
        if operation == "update_ticket":
            ticket = _stored(hive, ticket_id)
            assert ticket.status == "done"
            assert "routed" in ticket.tags
        else:
            assert not compute_ticket_path(ticket_id, hive).parent.exists()
    if not include_local:
        assert tree_snapshot(env.local) == local_before


@pytest.mark.parametrize("operation", ["update_ticket", "delete_ticket"], ids=["update", "delete"])
def test_ambiguous_batch_id_prevents_every_write(routing_env, routing_surface, operation):
    env = routing_env
    _duplicate_ticket(env)
    before = tree_snapshot(env.root)
    kwargs = {"status": "done", "add_tags": ["partial"]} if operation == "update_ticket" else {}

    # Valid local and foreign IDs precede the ambiguous ID: no earlier group may run.
    result = routing_surface.call(operation, ticket_ids=["b.qqq", "b.aaa", "b.bbb", "b.ccc"], **kwargs)

    assert tree_snapshot(env.root) == before
    _assert_conflict(result, env)


@pytest.mark.parametrize("status", ["done", "local_only"], ids=["successful_write", "rejected_write"])
def test_owning_scope_override_is_request_local(routing_env, routing_surface, status):
    env = routing_env

    async def mcp_probe():
        before = load_bees_config()
        result = await routing_surface.mcp_call("update_ticket", ticket_ids="b.aaa", status=status)
        # Stay in the same task; asyncio.run's task cleanup must not hide a leak.
        assert load_bees_config() == before
        return result

    before = load_bees_config()
    assert set(before.hives) == {"local"}
    assert before.status_values == ["local_only", "done"]
    if routing_surface.via == "mcp":
        result = asyncio.run(mcp_probe())
    else:
        result = routing_surface.call("update_ticket", ticket_ids="b.aaa", status=status)

    assert load_bees_config() == before
    if status == "done":
        assert result["status"] == "success", result
        assert _stored(env.alpha, "b.aaa").status == "done"
    else:
        assert result["status"] == "error", result
        assert result["error_type"] == "invalid_status"
        assert _stored(env.alpha, "b.aaa").status == "alpha_only"


def test_dependency_into_another_foreign_scope_is_refused_like_owner(routing_env, routing_surface):
    env = routing_env
    before = tree_snapshot(env.root)
    kwargs = {"ticket_ids": "b.aaa", "up_deps": ["b.bbb"]}

    owner_result = routing_surface.call("update_ticket", root=env.owner_a, **kwargs)
    assert owner_result["status"] == "error", owner_result
    assert owner_result["error_type"] == "invalid_dependency"
    assert tree_snapshot(env.root) == before
    queen_result = routing_surface.call("update_ticket", **kwargs)

    assert tree_snapshot(env.root) == before
    assert queen_result["status"] == "error", queen_result
    assert queen_result["error_type"] == owner_result["error_type"]
    assert _stored(env.alpha, "b.aaa").up_dependencies == []
    assert _stored(env.beta, "b.bbb").down_dependencies == []


# ---------------------------------------------------------------------------
# Engineer regressions: accepted code-review blockers, fix round 1 (b.11s).
# ---------------------------------------------------------------------------


def _add_registered_hive(scope, name, path):
    path.mkdir(parents=True)
    config = load_global_config()
    config["scopes"].setdefault(scope, {"hives": {}})["hives"][name] = {
        "path": str(path), "display_name": name.title(),
    }
    save_global_config(config)
    return path


@pytest.mark.parametrize("selection", ["unique_id", "owner_root"])
def test_shared_hive_name_disambiguated_by_ticket_id_or_owner_root(routing_env, routing_surface, selection):
    env = routing_env
    for root, ticket_id, status in (
        (env.queen, "b.iii", "local_only"),
        (env.owner_a, "b.ccc", "alpha_only"),
        (env.owner_b, "b.ddd", "beta_only"),
    ):
        ideas = _add_registered_hive(str(root), "ideas", root / "ideas")
        write_ticket_file(ideas, ticket_id, title="Scope's idea", status=status)
    target = compute_ticket_path("b.ccc", env.owner_a / "ideas")
    before = tree_snapshot(env.root)
    kwargs = {"hive": "ideas", "root": env.owner_a} if selection == "owner_root" else {}

    result = routing_surface.call("update_ticket", ticket_ids="b.ccc", status="done", add_tags=["selected"], **kwargs)

    assert result["status"] == "success", result
    ticket = _stored(env.owner_a / "ideas", "b.ccc")
    assert ticket.status == "done"
    assert ticket.tags == ["selected"]
    assert snapshot_diff(before, tree_snapshot(env.root)) == (
        set(), set(), {target.relative_to(env.root).as_posix()},
    )


@pytest.mark.parametrize("operation", ["move_bee", "clone_bee"])
def test_local_destination_keeps_foreign_sources_out_of_its_view(
    routing_env, routing_surface, operation,
):
    env = routing_env
    _add_registered_hive(str(env.queen), "archive", env.queen / "archive")
    _add_registered_hive(str(env.owner_a), "archive", env.owner_a / "archive")
    before = tree_snapshot(env.root)
    kwargs = {"bee_ids": ["b.aaa"]} if operation == "move_bee" else {"bee_id": "b.aaa"}

    result = routing_surface.call(operation, hive="archive", **kwargs)

    if operation == "move_bee":
        assert result == {
            "status": "success", "moved": [], "skipped": [], "not_found": ["b.aaa"], "failed": [],
        }
    else:
        assert result["status"] == "error", result
        assert result["error_type"] == "bee_not_found", result
    assert tree_snapshot(env.root) == before


@pytest.mark.parametrize("operation", ["move_bee", "clone_bee"])
def test_foreign_destination_uses_its_own_view_for_unseen_source(routing_env, routing_surface, operation):
    env = routing_env
    before = tree_snapshot(env.root)
    kwargs = {"bee_ids": ["b.aaa"]} if operation == "move_bee" else {"bee_id": "b.aaa"}

    control = routing_surface.call(operation, root=env.owner_b, hive="beta", **kwargs)
    result = routing_surface.call(operation, hive="beta", **kwargs)

    assert result == control
    assert tree_snapshot(env.root) == before


def test_move_keeps_all_sources_in_the_destination_view(routing_env, routing_surface):
    env = routing_env
    before = tree_snapshot(env.root)

    result = routing_surface.call("move_bee", bee_ids=["b.aaa", "b.bbb"], hive="beta")

    assert result == {
        "status": "success", "moved": [], "skipped": ["b.bbb"], "not_found": ["b.aaa"], "failed": [],
    }
    assert tree_snapshot(env.root) == before


@pytest.mark.parametrize("owner_suffix", ["", "/*", "/**"], ids=["exact", "shallow", "recursive"])
def test_owner_view_keeps_ancestor_hives_and_owner_settings(routing_env, routing_surface, owner_suffix):
    env = routing_env
    shared = _add_registered_hive(str(env.root) + "/**", "shared", env.root / "shared")
    write_ticket_file(shared, "b.ccc", title="Ancestor ticket", status="done")
    config = load_global_config()
    ancestor = config["scopes"][str(env.root) + "/**"]
    ancestor["status_values"] = ["ancestor_only", "done"]
    ancestor["child_tiers"] = {"t1": ["Ancestor", "Ancestors"]}
    if owner_suffix:
        config["scopes"][str(env.owner_a) + owner_suffix] = config["scopes"].pop(str(env.owner_a))
    save_global_config(config)

    result = routing_surface.call("update_ticket", ticket_ids="b.aaa", status="alpha_only", up_deps=["b.ccc"])

    assert result["status"] == "success", result
    assert _stored(env.alpha, "b.aaa").up_dependencies == ["b.ccc"]
    assert _stored(shared, "b.ccc").down_dependencies == ["b.aaa"]
    rejected = routing_surface.call("update_ticket", ticket_ids="b.aaa", status="ancestor_only")
    assert rejected["error_type"] == "invalid_status", rejected
    rejected = routing_surface.call(
        "create_ticket", ticket_type="Ancestor", title="Wrong tier", hive="alpha", parent="b.aaa",
    )
    assert rejected["error_type"] == "invalid_ticket_type", rejected


def test_delete_cleans_dependencies_in_an_ancestor_hive(routing_env, routing_surface):
    env = routing_env
    shared = _add_registered_hive(str(env.root) + "/**", "shared", env.root / "shared")
    write_ticket_file(shared, "b.ccc", title="Ancestor ticket", down_dependencies=["b.aaa"])
    write_ticket_file(env.alpha, "b.aaa", title="Alpha", up_dependencies=["b.ccc"])
    config = load_global_config()
    config["delete_with_dependencies"] = True
    save_global_config(config)

    result = routing_surface.call("delete_ticket", ticket_ids=["b.aaa"])

    assert result["deleted"] == ["b.aaa"], result
    assert _stored(shared, "b.ccc").down_dependencies == []


def test_registration_save_with_inherited_hives_stays_in_the_owner(routing_env, routing_surface):
    env = routing_env
    ancestor_key = str(env.root) + "/**"
    _add_registered_hive(ancestor_key, "shared", env.root / "shared")
    before = load_global_config()

    result = routing_surface.call("rename_hive", old_name="alpha", new_name="renamed")

    assert result["status"] == "success", result
    after = load_global_config()
    assert after["scopes"][ancestor_key] == before["scopes"][ancestor_key]
    assert set(after["scopes"][str(env.owner_a)]["hives"]) == {"renamed"}
    assert after["scopes"][str(env.owner_b)] == before["scopes"][str(env.owner_b)]


@pytest.mark.parametrize("operation,key", [("update_ticket", "updated"), ("delete_ticket", "deleted")])
@pytest.mark.parametrize("failure_first", [False, True], ids=["later_error", "first_error"])
def test_batch_retains_completed_groups_and_continues_after_a_group_error(
    routing_env, routing_surface, monkeypatch, operation, key, failure_first,
):
    from src import queen_write

    env = routing_env
    original = queen_write._call_in_scope

    async def fail_beta(fn, bound, scope, *args, **kwargs):
        if scope == str(env.owner_b):
            return {"status": "error", "error_type": "write_error", "message": "Beta storage unavailable"}
        return await original(fn, bound, scope, *args, **kwargs)

    monkeypatch.setattr(queen_write, "_call_in_scope", fail_beta)
    ids = ["b.bbb", "b.aaa", "b.qqq"] if failure_first else ["b.aaa", "b.bbb", "b.qqq"]
    kwargs = {"status": "done"} if operation == "update_ticket" else {}

    result = routing_surface.call(operation, ticket_ids=ids, **kwargs)

    assert result["status"] == "success", result
    assert result[key] == ["b.aaa", "b.qqq"]
    assert result["failed"] == [{"id": "b.bbb", "reason": "Beta storage unavailable"}]
    assert result["not_found"] == []
    assert _stored(env.beta, "b.bbb").status == "beta_only"
    for hive, tid in [(env.alpha, "b.aaa"), (env.local, "b.qqq")]:
        if operation == "update_ticket":
            assert _stored(hive, tid).status == "done"
        else:
            assert not compute_ticket_path(tid, hive).exists()


def test_only_group_error_keeps_the_original_error(routing_env, routing_surface, monkeypatch):
    from src import queen_write

    error = {"status": "error", "error_type": "write_error", "message": "Storage unavailable"}

    async def fail(*args, **kwargs):
        return error

    monkeypatch.setattr(queen_write, "_call_in_scope", fail)
    before = tree_snapshot(routing_env.root)
    result = routing_surface.call("update_ticket", ticket_ids=["b.aaa"], status="done")
    assert result == error
    assert tree_snapshot(routing_env.root) == before


def test_depth_dependent_wildcard_view_is_preflighted_before_any_group(routing_env, routing_surface):
    env = routing_env
    config = load_global_config()
    recursive_owner = str(env.owner_b) + "/**"
    config["scopes"][recursive_owner] = config["scopes"].pop(str(env.owner_b))
    shallow_ancestor = str(env.root) + "/*"
    config["scopes"][shallow_ancestor] = {"hives": {}}
    save_global_config(config)
    before = tree_snapshot(env.root)

    result = routing_surface.call("update_ticket", ticket_ids=["b.aaa", "b.bbb"], status="done")

    assert result["status"] == "error", result
    assert result["error_type"] == "config_conflict", result
    assert recursive_owner in result["message"]
    assert shallow_ancestor in result["message"]
    assert tree_snapshot(env.root) == before


def test_explicit_local_hive_does_not_fall_back_to_a_foreign_ticket(routing_env, routing_surface):
    env = routing_env
    _add_registered_hive(str(env.queen), "alpha", env.queen / "alpha")
    before = tree_snapshot(env.root)
    result = routing_surface.call("update_ticket", hive="alpha", ticket_ids="b.aaa", title="Must stay local")

    assert result["status"] == "error", result
    assert result["error_type"] == "ticket_not_found", result
    assert tree_snapshot(env.root) == before


@pytest.mark.parametrize("kwargs,error_type", [
    ({"title": "Cannot batch titles"}, "invalid_field"),
    ({"priority": "bad"}, "invalid_priority"),
])
def test_batch_wide_validation_precedes_every_group(routing_env, routing_surface, kwargs, error_type):
    before = tree_snapshot(routing_env.root)

    result = routing_surface.call("update_ticket", ticket_ids=["b.aaa", "b.bbb"], **kwargs)

    assert result["status"] == "error", result
    assert result["error_type"] == error_type, result
    assert tree_snapshot(routing_env.root) == before


@pytest.mark.parametrize("failure", ["config", "io", "unexpected"])
def test_late_exception_keeps_completed_batch_results(routing_env, routing_surface, monkeypatch, failure):
    from src import queen_write
    from src.config import ConfigLoadError

    env = routing_env
    original = queen_write._call_in_scope
    error = {
        "config": ConfigLoadError(env.root / "config.json", "Registry became unreadable"),
        "io": OSError("Registry became unreadable"),
        "unexpected": RuntimeError("Registry became unreadable"),
    }[failure]

    async def unavailable_beta(fn, bound, scope, *args, **kwargs):
        if scope == str(env.owner_b):
            raise error
        return await original(fn, bound, scope, *args, **kwargs)

    monkeypatch.setattr(queen_write, "_call_in_scope", unavailable_beta)
    result = routing_surface.call("update_ticket", ticket_ids=["b.aaa", "b.bbb"], status="done")

    assert result["status"] == "success", result
    assert result["updated"] == ["b.aaa"]
    assert result["failed"] == [{"id": "b.bbb", "reason": "Registry became unreadable"}]
    assert _stored(env.alpha, "b.aaa").status == "done"
    assert _stored(env.beta, "b.bbb").status == "beta_only"


@pytest.mark.parametrize("owner_suffix,visible", [("", True), ("/*", False)], ids=["exact", "shallow"])
def test_shallow_ancestor_only_inherits_at_depths_it_matches(routing_env, routing_surface, owner_suffix, visible):
    env = routing_env
    shared = _add_registered_hive(str(env.root) + "/*", "shared", env.root / "shared")
    write_ticket_file(shared, "b.ccc", title="Shared", status="done")
    config = load_global_config()
    if owner_suffix:
        config["scopes"][str(env.owner_a) + owner_suffix] = config["scopes"].pop(str(env.owner_a))
    save_global_config(config)
    before = tree_snapshot(env.root)

    result = routing_surface.call("update_ticket", ticket_ids="b.aaa", up_deps=["b.ccc"])

    if visible:
        assert result["status"] == "success", result
        assert _stored(shared, "b.ccc").down_dependencies == ["b.aaa"]
    else:
        assert result["error_type"] == "invalid_dependency", result
        assert tree_snapshot(env.root) == before


@pytest.mark.parametrize("ids", [["b.aaa", "b.bbb"], ["b.aaa", "b.bbb", "b.bbb"]], ids=["unique", "duplicate"])
def test_all_group_errors_keep_batch_shape_and_unique_failures(routing_env, routing_surface, monkeypatch, ids):
    from src import queen_write

    async def unavailable(*args, **kwargs):
        return {"status": "error", "error_type": "write_error", "message": "Storage unavailable"}

    monkeypatch.setattr(queen_write, "_call_in_scope", unavailable)
    before = tree_snapshot(routing_env.root)
    result = routing_surface.call("update_ticket", ticket_ids=ids, status="done")

    assert result == {
        "status": "success", "updated": [], "not_found": [], "failed": [
            {"id": "b.aaa", "reason": "Storage unavailable"},
            {"id": "b.bbb", "reason": "Storage unavailable"},
        ],
    }
    assert tree_snapshot(routing_env.root) == before


# Fix round 1b: locally visible hive names keep the caller's original view.


@pytest.mark.parametrize("operation", ["create_ticket", "update_ticket", "sanitize_hive", "move_bee", "clone_bee"])
def test_queen_uses_own_ideas_when_two_foreign_scopes_share_its_name(
    routing_env, routing_surface, operation,
):
    env = routing_env
    local_ideas = _add_registered_hive(str(env.queen), "ideas", env.queen / "ideas")
    for owner, tid, status in [(env.owner_a, "b.ccc", "alpha_only"), (env.owner_b, "b.ddd", "beta_only")]:
        hive = _add_registered_hive(str(owner), "ideas", owner / "ideas")
        write_ticket_file(hive, tid, title="Foreign idea", status=status)
    write_ticket_file(local_ideas, "b.iii", title="Local idea", status="local_only")
    if operation == "sanitize_hive":
        write_ticket_file(local_ideas, "b.iii", title="Local idea", status="local_only", guid=None)
    foreign_before = {str(root): tree_snapshot(root) for root in (env.owner_a, env.owner_b)}

    kwargs = {
        "create_ticket": {"ticket_type": "bee", "title": "New local idea", "status": "local_only"},
        "update_ticket": {"ticket_ids": "b.iii", "title": "Updated local idea", "status": "done"},
        "sanitize_hive": {},
        "move_bee": {"bee_ids": ["b.qqq"]},
        "clone_bee": {"bee_id": "b.qqq"},
    }[operation]

    result = routing_surface.call(operation, hive="ideas", **kwargs)

    assert result["status"] == "success", result
    assert {str(root): tree_snapshot(root) for root in (env.owner_a, env.owner_b)} == foreign_before
    if operation in ("create_ticket", "clone_bee"):
        ticket = _stored(local_ideas, result["ticket_id"])
        assert ticket.status == "local_only"
        assert ticket.title == ("New local idea" if operation == "create_ticket" else "Local ticket")
    elif operation == "update_ticket":
        ticket = _stored(local_ideas, "b.iii")
        assert (ticket.title, ticket.status) == ("Updated local idea", "done")
    elif operation == "sanitize_hive":
        assert _stored(local_ideas, "b.iii").guid
        assert any(fix["fix_type"] == "add_guid" for fix in result["fixes_applied"])
    else:
        assert result["moved"] == ["b.qqq"]
        assert not compute_ticket_path("b.qqq", env.local).exists()
        assert _stored(local_ideas, "b.qqq").title == "Local ticket"


# Fix round 2: local discovery precedes foreign parsing and filesystem probes.


@pytest.fixture
def unreadable_foreign_hive(routing_env):
    if os.geteuid() == 0:
        pytest.skip("Root bypasses directory search permissions")
    env = routing_env
    parent = env.root / "blocked"
    scope = str(env.root / "unrelated")
    hive = _add_registered_hive(scope, "unreadable", parent / "hive")
    write_ticket_file(hive, "b.zzz", title="Inaccessible foreign ticket")
    config = load_global_config()
    # Put the inaccessible hive before the real target, so discovery must
    # continue after a failure rather than merely tolerate one at the end.
    blocked_scope = config["scopes"].pop(scope)
    config["scopes"] = {scope: blocked_scope, **config["scopes"]}
    save_global_config(config)
    mode = stat.S_IMODE(parent.stat().st_mode)
    parent.chmod(0)
    try:
        with pytest.raises(PermissionError):
            hive.stat()
        yield SimpleNamespace(hive=hive, scope=scope)
    finally:
        parent.chmod(mode)


@pytest.mark.parametrize("operation,kwargs", [
    ("update_ticket", {"ticket_ids": "b.iii", "hive": "ideas", "status": "done"}),
    ("update_ticket", {"ticket_ids": "b.iii", "status": "done"}),
    ("append_ticket_body", {"ticket_id": "b.iii", "chunk": "Appended"}),
    ("delete_ticket", {"ticket_ids": ["b.iii"]}),
    ("move_bee", {"bee_ids": ["b.qqq"], "hive": "ideas"}),
    ("clone_bee", {"bee_id": "b.iii"}),
    ("clone_bee", {"bee_id": "b.qqq", "hive": "ideas"}),
    ("create_ticket", {"ticket_type": "bee", "title": "Local", "status": "local_only", "hive": "ideas"}),
    ("sanitize_hive", {"hive": "ideas"}),
], ids=["update_named", "update_id", "append", "delete", "move", "clone_id", "clone_named", "create", "sanitize"])
def test_local_write_ignores_unreadable_foreign_hive(
    routing_env, routing_surface, unreadable_foreign_hive, caplog, operation, kwargs,
):
    env = routing_env
    ideas = _add_registered_hive(str(env.queen), "ideas", env.queen / "ideas")
    seed_fields = {"guid": None} if operation == "sanitize_hive" else {}
    write_ticket_file(ideas, "b.iii", title="Local idea", status="local_only", **seed_fields)
    original_body = _stored(ideas, "b.iii").body
    foreign_before = {str(root): tree_snapshot(root) for root in (env.owner_a, env.owner_b)}

    result = routing_surface.call(operation, **kwargs)

    assert result["status"] == "success", result
    assert {str(root): tree_snapshot(root) for root in (env.owner_a, env.owner_b)} == foreign_before
    assert str(unreadable_foreign_hive.hive) not in caplog.text
    if operation == "update_ticket":
        assert _stored(ideas, "b.iii").status == "done"
    elif operation == "append_ticket_body":
        assert _stored(ideas, "b.iii").body == original_body + "Appended"
    elif operation == "delete_ticket":
        assert result["deleted"] == ["b.iii"]
        assert not compute_ticket_path("b.iii", ideas).exists()
    elif operation == "move_bee":
        assert result["moved"] == ["b.qqq"]
        assert compute_ticket_path("b.qqq", ideas).is_file()
    elif operation in ("clone_bee", "create_ticket"):
        assert compute_ticket_path(result["ticket_id"], ideas).is_file()
    elif operation == "sanitize_hive":
        assert _stored(ideas, "b.iii").guid
        assert any(fix["fix_type"] == "add_guid" for fix in result["fixes_applied"])


@pytest.mark.parametrize("ticket_ids", ["b.aaa", ["b.qqq", "b.aaa"]], ids=["single", "mixed_batch"])
def test_foreign_write_skips_unreadable_hive_and_only_probes_unresolved_ids(
    routing_env, routing_surface, unreadable_foreign_hive, monkeypatch, caplog, ticket_ids,
):
    from src import queen_write

    env = routing_env
    original = queen_write.build_ticket_path_map
    foreign_probes = []

    def track(ids, hive_collection):
        if any(config.path != str(env.local) for _, config in hive_collection):
            foreign_probes.append(set(ids))
        return original(ids, hive_collection=hive_collection)

    monkeypatch.setattr(queen_write, "build_ticket_path_map", track)
    result = routing_surface.call("update_ticket", ticket_ids=ticket_ids, status="done")

    assert result["status"] == "success", result
    assert result["updated"] == (["b.aaa"] if isinstance(ticket_ids, str) else ticket_ids)
    assert _stored(env.local, "b.qqq").status == ("local_only" if isinstance(ticket_ids, str) else "done")
    assert _stored(env.alpha, "b.aaa").status == "done"
    assert foreign_probes and all(ids == {"b.aaa"} for ids in foreign_probes)
    assert str(unreadable_foreign_hive.hive) in caplog.text
    assert "Skipping" in caplog.text


def test_unreadable_foreign_target_keeps_batch_not_found_shape(
    routing_env, routing_surface, unreadable_foreign_hive, caplog,
):
    before = tree_snapshot(routing_env.root)
    result = routing_surface.call("update_ticket", ticket_ids=["b.zzz", "b.xxx"], status="done")

    assert result == {"status": "success", "updated": [], "not_found": ["b.zzz", "b.xxx"], "failed": []}
    assert tree_snapshot(routing_env.root) == before
    assert str(unreadable_foreign_hive.hive) in caplog.text


@pytest.mark.parametrize("foreign_target", [False, True], ids=["local_named", "foreign_by_id"])
def test_write_does_not_parse_unrelated_foreign_settings(routing_env, routing_surface, foreign_target):
    env = routing_env
    config = load_global_config()
    config["scopes"][str(env.owner_b)]["status_values"] = "Invalid unrelated scope settings"
    save_global_config(config)

    tid = "b.aaa" if foreign_target else "b.qqq"
    kwargs = {} if foreign_target else {"hive": "local"}
    result = routing_surface.call("update_ticket", ticket_ids=tid, status="done", **kwargs)

    assert result["status"] == "success", result
    assert _stored(env.alpha if foreign_target else env.local, tid).status == "done"


@pytest.mark.parametrize("target_present", [True, False], ids=["other_hive", "missing_target"])
def test_foreign_discovery_skips_missing_hive(routing_env, routing_surface, caplog, target_present):
    env = routing_env
    missing = _add_registered_hive(str(env.root / "missing_owner"), "missing", env.root / "missing_hive")
    write_ticket_file(missing, "b.zzz", title="Moved foreign ticket")
    missing.rename(missing.with_name("relocated_hive"))
    tid = "b.aaa" if target_present else "b.zzz"
    before = tree_snapshot(env.root)

    result = routing_surface.call("update_ticket", ticket_ids=[tid, "b.xxx"], status="done")

    assert result == {
        "status": "success", "updated": [tid] if target_present else [],
        "not_found": ["b.xxx"] if target_present else [tid, "b.xxx"], "failed": [],
    }
    after = tree_snapshot(env.root)
    if target_present:
        assert _stored(env.alpha, tid).status == "done"
        target = compute_ticket_path(tid, env.alpha)
        assert snapshot_diff(before, after) == (set(), set(), {target.relative_to(env.root).as_posix()})
    else:
        assert after == before
    assert str(missing) in caplog.text
    assert "Skipping missing foreign hive" in caplog.text
