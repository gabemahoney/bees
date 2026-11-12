"""Index target resolution must fail before writing outside a registered hive."""

import pytest

from src.mcp_index_ops import _generate_index
from src.repo_context import repo_root_context


@pytest.mark.parametrize(
    "scope,hive_name",
    [
        pytest.param("unmatched", "ideas", id="hive_registered_in_other_scope"),
        pytest.param("unmatched", "Ghost Hive", id="unknown_hive_unmatched_scope"),
        pytest.param("no_config", "ghost", id="no_config_file"),
        pytest.param("unmatched", "absolute", id="absolute_path_name"),
        pytest.param("matched", "ghost", id="unknown_hive_matched_scope"),
    ],
)
async def test_generate_index_unresolved_hive(
    isolated_bees_env, tmp_path, monkeypatch, scope, hive_name
):
    """Regression b.5nf: unresolved names return hive_not_found and write nothing."""
    if scope != "no_config":
        isolated_bees_env.create_hive("ideas")
        isolated_bees_env.write_config()

    caller = tmp_path if scope == "matched" else tmp_path / "caller"
    caller.mkdir(exist_ok=True)
    server_cwd = tmp_path / "server"
    server_cwd.mkdir()
    monkeypatch.chdir(server_cwd)
    if hive_name == "absolute":
        hive_name = str(tmp_path / "absolute_hive")

    with repo_root_context(caller):
        result = await _generate_index(hive_name=hive_name, resolved_root=caller)

    # Includes server cwd, caller, the registered hive and the absolute target.
    assert list(tmp_path.rglob("index.md")) == []
    assert result["status"] == "error"
    assert result["error_type"] == "hive_not_found"
    assert f"Hive '{hive_name}'" in result["message"]
    if scope != "matched":
        assert f"matches '{caller}'" in result["message"]
        assert str(server_cwd) not in result["message"]


@pytest.mark.parametrize("has_config", [True, False], ids=["unmatched_scope", "no_config_file"])
async def test_generate_index_without_hive_requires_matching_scope(
    isolated_bees_env, tmp_path, monkeypatch, has_config
):
    """Regression b.5nf: no targets must report the caller's unmatched directory."""
    if has_config:
        isolated_bees_env.create_hive("ideas")
        isolated_bees_env.write_config()

    caller = tmp_path / "caller"
    caller.mkdir()
    server_cwd = tmp_path / "server"
    server_cwd.mkdir()
    monkeypatch.chdir(server_cwd)

    with repo_root_context(caller):
        result = await _generate_index(resolved_root=caller)

    assert list(tmp_path.rglob("index.md")) == []
    assert result["status"] == "error"
    assert result["error_type"] == "no_matching_scope"
    assert f"matches '{caller}'" in result["message"]
    assert str(server_cwd) not in result["message"]


async def test_generate_index_matched_scope_without_hives_succeeds(isolated_bees_env, tmp_path):
    """An intentionally empty scope remains a successful no-op."""
    isolated_bees_env.write_config()

    with repo_root_context(tmp_path):
        result = await _generate_index(resolved_root=tmp_path)

    assert result == {"status": "success", "skipped_hives": []}
    assert list(tmp_path.rglob("index.md")) == []
