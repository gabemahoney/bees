"""
Pytest configuration and fixtures for Bees tests.

See tests/TESTING.md for complete documentation on fixtures, mock patching strategy,
and decision trees for choosing the right fixture.
"""

import json
import shutil
from pathlib import Path

import pytest

from src.id_utils import generate_guid
from src.repo_context import repo_root_context


def write_scoped_config(
    global_bees_dir: Path,
    repo_root: Path,
    scope_data: dict,
    *,
    hive_child_tiers: dict[str, dict | None] | None = None,
    hive_status_values: dict[str, list[str] | None] | None = None,
    queries: dict[str, list] | None = None,
):
    """Write a scoped global config matching the given repo_root.

    Args:
        global_bees_dir: The (mocked) global ~/.bees/ directory
        repo_root: The repo root path to use as scope key (exact match)
        scope_data: Dict with hives, child_tiers, etc.
        hive_child_tiers: Optional dict mapping hive names to their per-hive child_tiers.
                         Keys must match hive names in scope_data["hives"].
                         Value of {} means bees-only (stops fallthrough).
                         Value of None (or key absent) means inherit from scope/global.
                         Example: {"features": {"t1": ["Epic", "Epics"]}, "bugs": {}}
        hive_status_values: Optional dict mapping hive names to their per-hive status_values.
                           Keys must match hive names in scope_data["hives"].
                           Value of [] means empty list (falls through to next level).
                           Value of None (or key absent) means omit key (inherit from scope/global).
                           Example: {"features": ["open", "closed"], "bugs": []}
        queries: Optional dict mapping query names to stage lists.
                 When provided, written into the scope entry alongside hives/child_tiers.
                 When omitted, no queries key appears in the scope entry.
    """
    # Inject per-hive child_tiers into hive entries if provided
    if hive_child_tiers:
        hives = scope_data.get("hives", {})
        for hive_name, tier_config in hive_child_tiers.items():
            if hive_name in hives:
                if tier_config is not None:
                    hives[hive_name]["child_tiers"] = tier_config
                # None means no child_tiers key (inherit from scope/global)

    # Inject per-hive status_values into hive entries if provided
    if hive_status_values:
        hives = scope_data.get("hives", {})
        for hive_name, status_vals in hive_status_values.items():
            if hive_name in hives:
                if status_vals is not None:
                    hives[hive_name]["status_values"] = status_vals
                # None means no status_values key (inherit from scope/global)

    # Inject queries into scope entry if provided
    if queries is not None:
        scope_data["queries"] = queries

    global_config = {
        "scopes": {str(repo_root): scope_data},
        "schema_version": "2.0",
    }
    config_path = global_bees_dir / "config.json"
    config_path.write_text(json.dumps(global_config, indent=2))


def write_global_queries(global_bees_dir: Path, queries: dict) -> None:
    """Write queries under the top-level queries key of config.json.

    Loads existing config (or creates minimal one), merges queries at the top level, and saves.
    Result is readable via load_global_config()["queries"].
    """
    config_path = global_bees_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"scopes": {}, "schema_version": "2.0"}
    config["queries"] = queries
    config_path.write_text(json.dumps(config, indent=2))


@pytest.fixture(scope="session", autouse=True)
def backup_global_config():
    """Backup and restore real ~/.bees/config.json to prevent test pollution."""
    real_config_path = Path.home() / ".bees" / "config.json"
    backup_path = Path.home() / ".bees" / "config.json.test_backup"

    if real_config_path.exists():
        shutil.copy2(real_config_path, backup_path)

    yield

    if backup_path.exists():
        shutil.copy2(backup_path, real_config_path)
        backup_path.unlink()


@pytest.fixture(autouse=True)
def mock_global_bees_dir(request, tmp_path, monkeypatch):
    """Redirect ~/.bees/ to tmp_path/global_bees/ so tests never touch real config.

    This is the critical isolation fixture. All config operations go through
    the mocked path instead of the real ~/.bees/ directory.

    Opt-out: @pytest.mark.needs_real_config
    """
    if "needs_real_config" in request.keywords:
        # Don't mock - use real config directory
        import src.config
        src.config._SCOPE_PATTERN_CACHE.clear()
        src.config._GLOBAL_CONFIG_CACHE = None
        src.config._GLOBAL_CONFIG_CACHE_MTIME = None
        return None

    global_bees = tmp_path / "global_bees"
    global_bees.mkdir()

    import src.config

    monkeypatch.setattr(src.config, "get_global_bees_dir", lambda: global_bees)
    monkeypatch.setattr(src.config, "get_global_config_path", lambda: global_bees / "config.json")

    # Clear the scope pattern cache to avoid stale compiled patterns
    src.config._SCOPE_PATTERN_CACHE.clear()

    # Clear the mtime-based global config cache for test isolation
    src.config._GLOBAL_CONFIG_CACHE = None
    src.config._GLOBAL_CONFIG_CACHE_MTIME = None

    # Clear any in-memory override to prevent leakage between tests
    src.config._GLOBAL_CONFIG_OVERRIDE = None

    return global_bees


@pytest.fixture(autouse=True)
def mock_git_repo_check(request, monkeypatch):
    """Mock git repo detection to allow tests in tmp_path. Opt-out: @pytest.mark.needs_real_git_check"""
    if "needs_real_git_check" in request.keywords:
        return

    def mock_get_repo_root(start_path: Path) -> Path:
        """Mock get_repo_root_from_path for test isolation."""
        current = start_path.resolve()

        while current != current.parent:
            if (current / ".git").exists() or (current / ".bees").exists():
                return current
            current = current.parent

        if (current / ".git").exists() or (current / ".bees").exists():
            return current

        return Path.cwd().resolve()

    # Patch get_repo_root_from_path in all modules that import it
    monkeypatch.setattr("src.repo_utils.get_repo_root_from_path", mock_get_repo_root)
    monkeypatch.setattr("src.mcp_server.get_repo_root_from_path", mock_get_repo_root)
    monkeypatch.setattr("src.mcp_ticket_ops.get_repo_root_from_path", mock_get_repo_root)
    monkeypatch.setattr("src.mcp_query_ops.get_repo_root_from_path", mock_get_repo_root)
    monkeypatch.setattr("src.mcp_hive_ops.get_repo_root_from_path", mock_get_repo_root)
    monkeypatch.setattr("src.cli.get_repo_root_from_path", mock_get_repo_root)


@pytest.fixture(autouse=True)
def clear_ticket_cache():
    """Clear the ticket read cache before each test for isolation."""
    import src.cache

    src.cache.clear()


@pytest.fixture(autouse=True)
def set_repo_root_context(request):
    """Set repo_root context to Path.cwd() for all tests. Opt-out: @pytest.mark.no_repo_context"""
    if "no_repo_context" in request.keywords:
        yield
        return

    with repo_root_context(Path.cwd()):
        yield


@pytest.fixture
def isolated_bees_env(tmp_path, monkeypatch, mock_global_bees_dir):
    """Create isolated Bees environment with BeesTestHelper for building test scenarios."""
    monkeypatch.chdir(tmp_path)

    class BeesTestHelper:
        def __init__(self, base_path, global_bees_dir):
            self.base_path = base_path
            self.global_bees_dir = global_bees_dir
            self.hives = {}

        def create_hive(self, hive_name: str, display_name: str | None = None):
            """Create a hive directory and register it."""
            hive_dir = self.base_path / hive_name
            hive_dir.mkdir(exist_ok=True)
            self.hives[hive_name] = {"path": str(hive_dir), "display_name": display_name or hive_name.title()}
            return hive_dir

        def write_config(self, child_tiers=None, status_values=None):
            """Write scoped global config with registered hives."""
            scope_data = {
                "hives": self.hives,
                "child_tiers": child_tiers or {},
            }
            if status_values is not None:
                scope_data["status_values"] = status_values
            write_scoped_config(self.global_bees_dir, self.base_path, scope_data)

        def create_ticket(
            self,
            hive_dir: Path,
            ticket_id: str,
            ticket_type: str,
            title: str,
            status: str = "open",
            guid: str | None = None,
            **extra_fields,
        ):
            """Create a ticket file with proper YAML frontmatter structure.

            Args:
                guid: Explicit GUID string. When None, auto-generates a valid GUID
                      from the ticket's short_id.
            """
            # Auto-generate GUID if not provided
            if guid is None:
                short_id = ticket_id.split(".", 1)[1] if "." in ticket_id else ticket_id
                guid = generate_guid(short_id)

            frontmatter = {
                "id": ticket_id,
                "type": ticket_type,
                "title": title,
                "status": status,
                "schema_version": "0.1",
                "created_at": "2026-01-30T10:00:00",
                "guid": guid,
                **extra_fields,
            }

            # Include egg: null for bee tickets so they pass linter integrity checks
            if ticket_type == "bee" and "egg" not in extra_fields:
                frontmatter["egg"] = None

            yaml_lines = ["---"]
            for key, value in frontmatter.items():
                if value is None:
                    yaml_lines.append(f"{key}: null")
                elif isinstance(value, str):
                    # Always quote schema_version to ensure it stays as string "0.1" not float 0.1
                    if key == "schema_version" or ":" in value or value.startswith("'"):
                        yaml_lines.append(f"{key}: '{value}'")
                    else:
                        yaml_lines.append(f"{key}: {value}")
                else:
                    yaml_lines.append(f"{key}: {value}")
            yaml_lines.append("---")
            yaml_lines.append("")
            yaml_lines.append(f"{title} body content.")

            # Use hierarchical structure: {hive_dir}/{ticket_id}/{ticket_id}.md
            ticket_dir = hive_dir / ticket_id
            ticket_dir.mkdir(parents=True, exist_ok=True)
            ticket_file = ticket_dir / f"{ticket_id}.md"
            ticket_file.write_text("\n".join(yaml_lines))
            return ticket_file

        def create_cemetery(self, hive_dir: Path, tickets: list[tuple] | None = None) -> Path:
            """Create a cemetery directory inside a hive, optionally with archived ticket files.

            Args:
                hive_dir: Path to the hive directory.
                tickets: Optional list of (filename, content) tuples to write inside cemetery/.

            Returns:
                Path to the created cemetery/ directory.
            """
            cemetery = hive_dir / "cemetery"
            cemetery.mkdir(exist_ok=True)
            if tickets:
                for filename, content in tickets:
                    (cemetery / filename).write_text(content)
            return cemetery

    helper = BeesTestHelper(tmp_path, mock_global_bees_dir)
    with repo_root_context(tmp_path):
        yield helper


@pytest.fixture
def mock_mcp_context(tmp_path):
    """Factory fixture for creating mock MCP Context objects. Returns create_mock_context(repo_path=None)."""
    from unittest.mock import Mock

    def create_mock_context(repo_path=None):
        """Create a mock context for the given repo path (defaults to tmp_path)."""
        if repo_path is None:
            repo_path = tmp_path

        ctx = Mock()
        mock_root = Mock()
        mock_root.uri = f"file://{repo_path}"

        async def mock_list_roots():
            return [mock_root]

        ctx.list_roots = mock_list_roots
        return ctx

    return create_mock_context


@pytest.fixture(scope="function")
def bees_repo(tmp_path):
    """Minimal bees repo: tmp_path with .git/ directory. Foundation for parameterized fixtures."""
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)
    yield tmp_path


# ============================================================================
# PARAMETERIZED FIXTURES
# ============================================================================


@pytest.fixture(scope="function", params=["bees_only", "two_tier", "three_tier", "four_tier"])
def hive_tier_config(request, bees_repo, monkeypatch, mock_global_bees_dir):
    """
    PARAMETERIZED: Tests 4 tier configs (bees-only, 2-tier, 3-tier, 4-tier).
    Returns (repo_root, hive_path, tier_config_dict).
    """
    from tests.test_constants import HIVE_BACKEND

    repo_root = bees_repo
    monkeypatch.chdir(repo_root)
    hive_path = repo_root / HIVE_BACKEND
    hive_path.mkdir(parents=True, exist_ok=True)

    # Create .hive identity marker
    hive_identity_dir = hive_path / ".hive"
    hive_identity_dir.mkdir(parents=True, exist_ok=True)
    identity_data = {"normalized_name": HIVE_BACKEND, "display_name": "Backend", "created_at": "2026-02-05T00:00:00"}
    (hive_identity_dir / "identity.json").write_text(json.dumps(identity_data, indent=2))

    tier_configs = {
        "bees_only": {},
        "two_tier": {"t1": ["Task", "Tasks"]},
        "three_tier": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
        "four_tier": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"], "t3": ["Work Item", "Work Items"]},
    }

    tier_config = tier_configs[request.param]

    scope_data = {
        "hives": {HIVE_BACKEND: {"path": str(hive_path), "display_name": "Backend"}},
        "child_tiers": tier_config,
    }
    write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

    with repo_root_context(repo_root):
        yield (repo_root, hive_path, tier_config)


@pytest.fixture(scope="function", params=["two_hives_isolated", "two_hives_connected", "three_hives_mixed"])
def multi_hive_config(request, bees_repo, monkeypatch, mock_global_bees_dir):
    """
    PARAMETERIZED: Tests 3 multi-hive scenarios (isolated, connected, mixed).
    Returns (repo_root, hive_paths_list, config_dict).
    """
    from tests.test_constants import HIVE_BACKEND, HIVE_FRONTEND

    repo_root = bees_repo
    monkeypatch.chdir(repo_root)

    if request.param == "two_hives_isolated":
        hive_names = [HIVE_BACKEND, HIVE_FRONTEND]
        tier_config = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}

    elif request.param == "two_hives_connected":
        hive_names = [HIVE_BACKEND, HIVE_FRONTEND]
        tier_config = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}

    else:  # three_hives_mixed
        hive_names = [HIVE_BACKEND, HIVE_FRONTEND, "api"]
        tier_config = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"], "t3": ["Work Item", "Work Items"]}

    hive_paths = []
    hives_config = {}

    for hive_name in hive_names:
        hive_path = repo_root / hive_name
        hive_path.mkdir(parents=True, exist_ok=True)

        # Create .hive identity marker
        hive_identity_dir = hive_path / ".hive"
        hive_identity_dir.mkdir(parents=True, exist_ok=True)
        identity_data = {
            "normalized_name": hive_name,
            "display_name": hive_name.title(),
            "created_at": "2026-02-05T00:00:00",
        }
        (hive_identity_dir / "identity.json").write_text(json.dumps(identity_data, indent=2))

        hive_paths.append(hive_path)
        hives_config[hive_name] = {"path": str(hive_path), "display_name": hive_name.title()}

    scope_data = {
        "hives": hives_config,
        "child_tiers": tier_config,
    }
    write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

    with repo_root_context(repo_root):
        yield (repo_root, hive_paths, scope_data)


# ============================================================================
# CONSOLIDATED SETUP FIXTURES
# ============================================================================


@pytest.fixture(
    scope="function",
    params=[
        "hive_override_epics",
        "hive_bees_only_override",
        "hive_inherits_scope",
        "mixed_hive_tiers",
    ],
)
def per_hive_tier_config(request, bees_repo, monkeypatch, mock_global_bees_dir):
    """
    PARAMETERIZED: Tests 4 per-hive child_tiers resolution scenarios.

    Scenarios:
        - hive_override_epics: features hive overrides scope with Epic/Task tiers
        - hive_bees_only_override: bugs hive uses empty {} to force bees-only
        - hive_inherits_scope: backend hive has no child_tiers key, inherits scope default
        - mixed_hive_tiers: multiple hives each with different tier configs

    Returns:
        tuple: (repo_root, hive_paths_dict, scope_child_tiers, hive_child_tiers_dict)
            - hive_paths_dict: {hive_name: Path}
            - scope_child_tiers: the scope-level child_tiers
            - hive_child_tiers_dict: {hive_name: expected_effective_tiers}
    """
    from tests.test_constants import (
        HIVE_BACKEND,
        HIVE_BUGS,
        HIVE_FEATURES,
        HIVE_TIER_BEES_ONLY,
        HIVE_TIER_EPICS,
        SCOPE_TIER_DEFAULT,
    )

    repo_root = bees_repo
    monkeypatch.chdir(repo_root)

    def _make_hive(name):
        hive_path = repo_root / name
        hive_path.mkdir(parents=True, exist_ok=True)
        hive_identity_dir = hive_path / ".hive"
        hive_identity_dir.mkdir(parents=True, exist_ok=True)
        identity_data = {"normalized_name": name, "display_name": name.title(), "created_at": "2026-02-05T00:00:00"}
        (hive_identity_dir / "identity.json").write_text(json.dumps(identity_data, indent=2))
        return hive_path

    if request.param == "hive_override_epics":
        # features hive overrides scope with Epic/Task
        hive_paths = {HIVE_FEATURES: _make_hive(HIVE_FEATURES)}
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {HIVE_FEATURES: HIVE_TIER_EPICS}
        expected = {HIVE_FEATURES: HIVE_TIER_EPICS}

    elif request.param == "hive_bees_only_override":
        # bugs hive forces bees-only with empty {}
        hive_paths = {HIVE_BUGS: _make_hive(HIVE_BUGS)}
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {HIVE_BUGS: HIVE_TIER_BEES_ONLY}
        expected = {HIVE_BUGS: HIVE_TIER_BEES_ONLY}

    elif request.param == "hive_inherits_scope":
        # backend hive has no child_tiers key → inherits scope default
        hive_paths = {HIVE_BACKEND: _make_hive(HIVE_BACKEND)}
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {}  # no hive-level overrides
        expected = {HIVE_BACKEND: SCOPE_TIER_DEFAULT}

    else:  # mixed_hive_tiers
        # features=Epic/Task, bugs=bees-only, backend=inherits scope
        hive_paths = {
            HIVE_FEATURES: _make_hive(HIVE_FEATURES),
            HIVE_BUGS: _make_hive(HIVE_BUGS),
            HIVE_BACKEND: _make_hive(HIVE_BACKEND),
        }
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {HIVE_FEATURES: HIVE_TIER_EPICS, HIVE_BUGS: HIVE_TIER_BEES_ONLY}
        expected = {HIVE_FEATURES: HIVE_TIER_EPICS, HIVE_BUGS: HIVE_TIER_BEES_ONLY, HIVE_BACKEND: SCOPE_TIER_DEFAULT}

    hives_config = {name: {"path": str(path), "display_name": name.title()} for name, path in hive_paths.items()}
    scope_data = {"hives": hives_config, "child_tiers": scope_tiers}
    write_scoped_config(mock_global_bees_dir, repo_root, scope_data, hive_child_tiers=per_hive)

    with repo_root_context(repo_root):
        yield (repo_root, hive_paths, scope_tiers, expected)


@pytest.fixture
def hive_env(tmp_path, monkeypatch, mock_global_bees_dir):
    """
    Complete single-hive environment with .git, backend hive, and t1/t2 child tiers.

    Yields:
        tuple: (repo_root: Path, hive_path: Path, hive_name: str)
    """
    monkeypatch.chdir(tmp_path)

    # Create .git directory (for repo detection)
    (tmp_path / ".git").mkdir()

    # Create backend hive directory
    hive_dir = tmp_path / "tickets" / "backend"
    hive_dir.mkdir(parents=True)

    # Create .hive marker
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir()
    identity_data = {"normalized_name": "backend", "display_name": "Backend", "created_at": "2026-02-05T00:00:00"}
    (hive_marker / "identity.json").write_text(json.dumps(identity_data, indent=2))

    # Write scoped global config
    scope_data = {
        "hives": {"backend": {"path": str(hive_dir), "display_name": "Backend", "created_at": "2026-02-05T00:00:00"}},
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

    with repo_root_context(tmp_path):
        yield tmp_path, hive_dir, "backend"


@pytest.fixture
def cli_runner(capsys):
    """Invoke src.cli.main() with a given argv list; returns (stdout_str, exit_code)."""

    def run(argv):
        import sys
        from unittest.mock import patch
        from src.cli import main

        with patch.object(sys, "argv", ["bees"] + argv):
            try:
                main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code if e.code is not None else 0

        captured = capsys.readouterr()
        return captured.out.strip(), exit_code

    return run
