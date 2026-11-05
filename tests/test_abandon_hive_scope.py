"""
Regression tests for Bug b.v2j (GH#31): dead or emptied scopes can't be removed.

PURPOSE:
abandon-hive deletes a scope key left fully empty after removing the hive, and
takes an explicit scope selector (CLI --scope, MCP scope) that names an exact
config key, so a scope whose folder is gone can be abandoned from anywhere.

SCOPE - Tests that belong here:
- Emptied scope key removal by _abandon_hive, and what keeps a scope
- An emptied scope no longer hiding a broader scope's child_tiers
- _abandon_hive / CLI abandon-hive --scope / MCP abandon_hive scope on a deleted folder

SCOPE - Tests that DON'T belong here:
- cwd-resolved single and multi-scope abandon -> test_mcp_server.py
"""

import copy
import json
import shutil
from unittest.mock import Mock

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from src.config import load_global_config
from src.mcp_hive_ops import _abandon_hive
from tests.conftest import write_multi_scope_config

T1 = {"t1": ["Task", "Tasks"]}


def _hive(base, name):
    return {"path": str(base / "wt" / ".bees" / name), "display_name": name}


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Resolved tmp_path; cwd is base/other, which no `base/wt/**` scope matches. base/wt does not exist."""
    base = tmp_path.resolve()
    (base / "other").mkdir()
    monkeypatch.chdir(base / "other")
    return base


@pytest.fixture
def dead_scope(base, mock_global_bees_dir):
    """Config with one scope, `base/wt/**`, holding only hive `issues`; returns the pattern."""
    pattern = f"{base}/wt/**"
    write_multi_scope_config(mock_global_bees_dir, {pattern: {"hives": {"issues": _hive(base, "issues")}}})
    return pattern


class TestEmptiedScopeRemoved:
    @pytest.mark.parametrize(
        "extra,kept",
        [
            pytest.param({}, False, id="only_hive_key_removed"),
            pytest.param({"hives": {"keep": {"path": "/k", "display_name": "keep"}}}, True, id="other_hive_kept"),
            pytest.param({"child_tiers": T1}, True, id="child_tiers_kept"),
            pytest.param({"child_tiers": {}}, True, id="empty_child_tiers_kept"),
            pytest.param({"status_values": ["open", "done"]}, True, id="status_values_kept"),
            pytest.param({"queries": {"q": {"stages": [["type=bee"]]}}}, True, id="queries_kept"),
        ],
    )
    async def test_abandon_removes_only_fully_empty_scope(self, base, mock_global_bees_dir, extra, kept):
        pattern = f"{base}/wt/**"
        (base / "wt").mkdir()
        scope = {**extra, "hives": {"wtbugs": _hive(base, "wtbugs"), **extra.get("hives", {})}}
        write_multi_scope_config(mock_global_bees_dir, {pattern: scope})

        result = await _abandon_hive("wtbugs", resolved_root=base / "wt")

        assert result["status"] == "success"
        scopes = load_global_config()["scopes"]
        if kept:
            expected = copy.deepcopy(scope)
            expected["hives"].pop("wtbugs")
            assert scopes[pattern] == expected
        else:
            assert pattern not in scopes

    def test_emptied_scope_no_longer_hides_broader_child_tiers(
        self, base, mock_global_bees_dir, cli_runner, monkeypatch
    ):
        """Documented teardown, then a folder recreated at the path sees the broader scope's tiers.

        wtbugs is registered by a real colonize-hive, so a scope-level key it adds would keep the scope.
        """
        write_multi_scope_config(mock_global_bees_dir, {
            f"{base}/**": {"hives": {"main": {"path": str(base / "main"), "display_name": "main"}}, "child_tiers": T1},
        })
        (base / "wt").mkdir()
        monkeypatch.chdir(base / "wt")
        _, exit_code = cli_runner([
            "colonize-hive", "--name", "wtbugs", "--path", str(base / "wt" / ".bees" / "wtbugs"),
            "--scope", f"{base}/wt/**",
        ])
        assert exit_code == 0
        assert "wtbugs" in load_global_config()["scopes"][f"{base}/wt/**"]["hives"]
        _, exit_code = cli_runner(["abandon-hive", "--hive", "wtbugs"])
        assert exit_code == 0
        monkeypatch.chdir(base / "other")
        shutil.rmtree(base / "wt")
        (base / "wt").mkdir()
        monkeypatch.chdir(base / "wt")

        stdout, exit_code = cli_runner(["get-types"])

        assert exit_code == 0
        assert json.loads(stdout)["scope"] == T1
        assert f"{base}/wt/**" not in load_global_config()["scopes"]


class TestAbandonByScope:
    async def test_dead_scope_abandoned_from_unrelated_root(self, base, dead_scope):
        result = await _abandon_hive("issues", resolved_root=base / "other", scope=dead_scope)

        assert result["status"] == "success"
        assert result["scopes_modified"] == 1
        assert result["scopes"] == [dead_scope]
        assert result["path"] == str(base / "wt" / ".bees" / "issues")
        assert dead_scope not in load_global_config()["scopes"]

    async def test_scope_selects_only_the_exact_key(self, base, mock_global_bees_dir):
        """With scope, other scopes matching the root keep the hive (no cwd/glob resolution)."""
        broad, narrow = f"{base}/**", f"{base}/wt/**"
        write_multi_scope_config(mock_global_bees_dir, {
            broad: {"hives": {"issues": _hive(base, "issues")}, "child_tiers": T1},
            narrow: {"hives": {"issues": _hive(base, "issues")}},
        })

        result = await _abandon_hive("issues", resolved_root=base / "other", scope=narrow)

        assert result["scopes"] == [narrow]
        scopes = load_global_config()["scopes"]
        assert narrow not in scopes
        assert "issues" in scopes[broad]["hives"]

    @pytest.mark.parametrize(
        "suffix,hive,error_type",
        [
            pytest.param("/nope/**", "issues", "scope_not_found", id="unknown_scope"),
            pytest.param("/wt", "issues", "scope_not_found", id="pattern_not_normalized"),
            pytest.param("/wt/**", "missing", "hive_not_found", id="hive_not_in_scope"),
        ],
    )
    async def test_scope_errors_leave_config_unchanged(
        self, base, dead_scope, mock_global_bees_dir, suffix, hive, error_type
    ):
        before = (mock_global_bees_dir / "config.json").read_text()
        scope = f"{base}{suffix}"

        result = await _abandon_hive(hive, resolved_root=base / "other", scope=scope)

        assert result["status"] == "error"
        assert result["error_type"] == error_type
        assert scope in result["message"]
        if error_type == "scope_not_found":
            assert "config.json" in result["message"]
        else:
            assert hive in result["message"]
        assert (mock_global_bees_dir / "config.json").read_text() == before


class TestAbandonByScopeAdapters:
    @pytest.mark.parametrize(
        "suffix,exit_code,status",
        [
            pytest.param("/wt/**", 0, "success", id="dead_scope_removed"),
            pytest.param("/nope/**", 1, "error", id="unknown_scope"),
        ],
    )
    def test_cli_abandon_hive_scope(self, base, dead_scope, cli_runner, suffix, exit_code, status):
        stdout, code = cli_runner(["abandon-hive", "--hive", "issues", "--scope", f"{base}{suffix}"])

        assert code == exit_code
        assert json.loads(stdout)["status"] == status
        assert (dead_scope in load_global_config()["scopes"]) == (status == "error")

    @pytest.mark.parametrize(
        "root_source", ["roots", "repo_root_without_roots", "cwd_without_ctx"]
    )
    async def test_mcp_scope_beats_the_caller_root(
        self, base, mock_global_bees_dir, mock_mcp_context, monkeypatch, root_source
    ):
        """The caller's root (from Roots, repo_root or cwd) is a live dir whose own scope also holds the
        hive; scope names the dead key, so only that key is removed and the caller's scope keeps the hive."""
        from src.mcp_server import abandon_hive

        live = base / "live"
        live.mkdir()
        dead, decoy = f"{base}/wt/**", f"{live}/**"
        write_multi_scope_config(mock_global_bees_dir, {
            dead: {"hives": {"issues": _hive(base, "issues")}},
            decoy: {"hives": {"issues": _hive(base, "issues")}},
        })
        repo_root = None
        if root_source == "roots":
            ctx = mock_mcp_context(live)
        elif root_source == "repo_root_without_roots":
            async def list_roots():
                raise McpError(ErrorData(code=-32601, message="Method not found"))
            ctx = Mock()
            ctx.list_roots = list_roots
            repo_root = str(live)
        else:
            ctx = None
            monkeypatch.chdir(live)

        result = await abandon_hive(hive="issues", ctx=ctx, repo_root=repo_root, scope=dead)

        assert result["status"] == "success"
        assert result["scopes"] == [dead]
        scopes = load_global_config()["scopes"]
        assert dead not in scopes
        assert "issues" in scopes[decoy]["hives"]
