"""
Pytest configuration and fixtures for Bees tests.

See tests/TESTING.md for complete documentation on fixtures, mock patching strategy,
and decision trees for choosing the right fixture.
"""

import atexit
import json
import logging
import os
import shutil
import site
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

# ============================================================================
# HOME ISOLATION (must run before any `src` import)
# ============================================================================
# The suite never reads or writes the real home directory. HOME (USERPROFILE on
# Windows) points at a temp dir for the whole session, so ~/.bees/, its config
# and mcp.log, and ~/.claude/ resolve there, in this process and in every
# subprocess, which inherits os.environ. This runs at conftest import, not in a
# fixture or pytest_configure: those run after the `src` imports below, and
# importing src.mcp_server creates ~/.bees/ and sets up logging into it.
# pytest imports this file before any test module; each pytest-xdist worker
# imports it on its own and gets its own temp home.

_REAL_HOMES = {os.path.expanduser("~")}
try:
    import pwd

    _REAL_HOMES.add(pwd.getpwuid(os.getuid()).pw_dir)  # used when HOME is unset
except (ImportError, KeyError):
    pass

ISOLATED_HOME = Path(tempfile.mkdtemp(prefix="bees-test-home-")).resolve()
# Also deleted when pytest_unconfigure never runs (failed import below, --version, usage error)
atexit.register(shutil.rmtree, ISOLATED_HOME, ignore_errors=True)
_SAVED_HOME_ENV = {var: os.environ.get(var) for var in ("HOME", "USERPROFILE", "PYTHONUSERBASE")}
# Subprocesses outside a virtualenv keep finding packages installed with `pip install --user`
os.environ.setdefault("PYTHONUSERBASE", site.getuserbase())
os.environ["HOME"] = os.environ["USERPROFILE"] = str(ISOLATED_HOME)

# Only the paths bees uses under a home are guarded: the checkout, the virtualenv
# and tool caches may live under the real home and are read legitimately.
_REAL_HOME_KEYS = {
    os.path.normcase(resolve(home)) for home in _REAL_HOMES for resolve in (os.path.abspath, os.path.realpath)
}
_GUARDED_PATHS = tuple(
    os.path.join(home, entry) for home in _REAL_HOME_KEYS for entry in (".bees", ".claude", ".claude.json")
)
# Audit event -> (index of a path argument, index of its dir_fd argument or None if it has none), per path.
_PATH_EVENTS = {
    **dict.fromkeys(("open", "os.listdir", "os.scandir", "os.truncate"), ((0, None),)),
    **dict.fromkeys(("os.remove", "os.rmdir", "shutil.rmtree"), ((0, 1),)),
    **dict.fromkeys(("os.mkdir", "os.chmod"), ((0, 2),)),
    "os.utime": ((0, 3),),
    **dict.fromkeys(("os.rename", "os.link"), ((0, 2), (1, 3))),
    "os.symlink": ((0, None), (1, 2)),
    **dict.fromkeys(("shutil.copyfile", "shutil.copytree", "shutil.move"), ((0, None), (1, None))),
}
_real_home_access: list[str] = []
_guard_active = True


class RealHomeAccessError(RuntimeError):
    """A test touched a guarded path under the real home. Not an OSError, which callers may swallow."""


def _guarded_path(path) -> str | None:
    """The absolute form of `path` if it is a guarded real-home path, else None."""
    try:
        path = os.path.abspath(os.fsdecode(path))
    except (TypeError, ValueError, OSError):
        return None
    key = os.path.normcase(path)
    return path if any(key == guarded or key.startswith(guarded + os.sep) for guarded in _GUARDED_PATHS) else None


def _relative_to_cwd(event: str, args: tuple, index: int, dir_fd_index: int | None) -> bool:
    """Whether a relative path argument of an audit event resolves against the cwd.

    It doesn't when it is relative to a dir_fd (shutil.rmtree and os.fwalk work on bare entry names
    that way) or to an unknown base: os.open() reports no dir_fd, a relative link target is
    relative to the link. Those relative paths are not checked; absolute ones always are.
    """
    if event == "open":
        return isinstance(args[1], str)  # open() reports its mode; os.open() reports None
    if event == "os.symlink" and index == 0:
        return False
    dir_fd = args[dir_fd_index] if dir_fd_index is not None and dir_fd_index < len(args) else None
    return dir_fd in (None, -1)  # -1 (or None) is "no dir_fd given"


def _real_home_audit_hook(event: str, args: tuple) -> None:
    """Block and record file operations on guarded real-home paths, before they happen."""
    if not _guard_active:
        return
    for index, dir_fd_index in _PATH_EVENTS.get(event, ()):
        path = args[index]
        if not isinstance(path, (str, bytes, os.PathLike)):
            continue  # a file descriptor
        if not os.path.isabs(path) and not _relative_to_cwd(event, args, index, dir_fd_index):
            continue
        guarded = _guarded_path(path)
        if guarded:
            message = f"{event} on {guarded}: tests must not touch the real home directory"
            _real_home_access.append(message)
            raise RealHomeAccessError(message)


sys.addaudithook(_real_home_audit_hook)


def _home_resolution_problems() -> list[str]:
    resolved = {
        "Path.home()": Path.home(),
        "os.path.expanduser('~')": Path(os.path.expanduser("~")),
        "src.config.get_global_bees_dir()": _unpatched_get_global_bees_dir(),
    }
    return [
        f"{name} resolves to {path}, in the real home directory"
        for name, path in resolved.items()
        if os.path.normcase(os.path.abspath(path)) in _REAL_HOME_KEYS or _guarded_path(path)
    ]


def pytest_sessionfinish(session):
    """Fail the run if anything touched the real home, also outside a test (imports, collection)."""
    if _real_home_access:
        if session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED  # keep a worse status (interrupted, internal error)
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_sep("=", "real home directory touched", red=True)
            reporter.write_line("\n".join(_real_home_access), red=True)


def pytest_unconfigure(config):
    """Close log files in the temp home, restore HOME/USERPROFILE/PYTHONUSERBASE and delete the temp home."""
    global _guard_active
    _guard_active = False
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename).is_relative_to(ISOLATED_HOME):
            root_logger.removeHandler(handler)
            handler.close()
    for var, value in _SAVED_HOME_ENV.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value
    shutil.rmtree(ISOLATED_HOME, ignore_errors=True)


from src.config import GLOBAL_SCHEMA_VERSION
from src.config import get_global_bees_dir as _unpatched_get_global_bees_dir
from src.id_utils import generate_guid
from src.mcp_hive_ops import write_identity
from src.repo_context import repo_root_context


def build_query(stages: list[list[str]], report: list[str] | None = None) -> dict:
    """Build a query dict in the storage format used by config helpers.

    Args:
        stages: List of pipeline stages (each stage is a list of term strings)
        report: Optional report field list

    Returns:
        Dict with "stages" key and optional "report" key
    """
    q: dict = {"stages": stages}
    if report is not None:
        q["report"] = report
    return q


def write_scoped_config(
    global_bees_dir: Path,
    repo_root: Path,
    scope_data: dict,
    *,
    hive_child_tiers: dict[str, dict | None] | None = None,
    hive_status_values: dict[str, list[str] | None] | None = None,
    queries: dict[str, dict] | None = None,
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
        queries: Optional dict mapping query names to query dicts ({"stages": [...]}).
                 When provided, written into the scope entry alongside hives/child_tiers.
                 When omitted, no queries key appears in the scope entry.
    """
    # Inject queries into scope entry if provided
    if queries is not None:
        scope_data["queries"] = queries

    # Extract child_tiers/status_values from inline hive entries before writing config.
    # These fields now live in identity.json, not config.json hive entries.
    hives = scope_data.get("hives", {})
    for hive_name, hive_entry in hives.items():
        if isinstance(hive_entry, dict):
            inline_ct = hive_entry.pop("child_tiers", None)
            inline_sv = hive_entry.pop("status_values", None)
            if inline_ct is not None:
                hive_child_tiers = hive_child_tiers or {}
                hive_child_tiers.setdefault(hive_name, inline_ct)
            if inline_sv is not None:
                hive_status_values = hive_status_values or {}
                hive_status_values.setdefault(hive_name, inline_sv)

    global_config = {
        "scopes": {str(repo_root): scope_data},
        "schema_version": GLOBAL_SCHEMA_VERSION,
    }
    config_path = global_bees_dir / "config.json"
    config_path.write_text(json.dumps(global_config, indent=2))

    # Write hive-level child_tiers/status_values to identity.json
    for hive_name in hives:
        hive_ct = (hive_child_tiers or {}).get(hive_name)
        hive_sv = (hive_status_values or {}).get(hive_name)
        if hive_ct is None and hive_sv is None:
            continue
        hive_path = Path(hives[hive_name].get("path", ""))
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir(parents=True, exist_ok=True)
        identity_data: dict = {
            "normalized_name": hive_name,
            "display_name": hives[hive_name].get("display_name", hive_name.title()),
            "created_at": hives[hive_name].get("created_at", "2026-02-05T00:00:00"),
        }
        if hive_ct is not None:
            identity_data["child_tiers"] = hive_ct
        if hive_sv is not None:
            identity_data["status_values"] = hive_sv
        write_identity(hive_marker, identity_data)


def write_multi_scope_config(global_bees_dir: Path, scopes_dict: dict) -> None:
    """Write a global config with scopes_dict as the scopes value.

    Unlike write_scoped_config, this function accepts arbitrary scope keys and
    does not restrict to a single repo_root. Use this when tests need multiple
    scope patterns (e.g. wildcards alongside exact keys) in one config.json.

    Args:
        global_bees_dir: The (mocked) global ~/.bees/ directory.
        scopes_dict: The full scopes mapping to write as the "scopes" value.
                     Keys may be any scope pattern strings.
    """
    global_config = {
        "scopes": scopes_dict,
        "schema_version": GLOBAL_SCHEMA_VERSION,
    }
    config_path = global_bees_dir / "config.json"
    config_path.write_text(json.dumps(global_config, indent=2))


def write_global_queries(global_bees_dir: Path, queries: dict[str, dict]) -> None:
    """Write queries under the top-level queries key of config.json.

    Args:
        global_bees_dir: The (mocked) global ~/.bees/ directory
        queries: Dict mapping query names to query dicts ({"stages": [...]})

    Loads existing config (or creates minimal one), merges queries at the top level, and saves.
    Result is readable via load_global_config()["queries"].
    """
    config_path = global_bees_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"scopes": {}, "schema_version": GLOBAL_SCHEMA_VERSION}
    config["queries"] = queries
    config_path.write_text(json.dumps(config, indent=2))


def write_global_settings(global_bees_dir: Path, **settings) -> None:
    """Merge top-level global settings (e.g. ``status_values``, ``child_tiers``) into config.json.

    Keeps the ``scopes`` already written. Global values are the third level of the
    hive > scope > global resolution of status_values and child_tiers.
    """
    config_path = global_bees_dir / "config.json"
    config = json.loads(config_path.read_text())
    config.update(settings)
    config_path.write_text(json.dumps(config, indent=2))


def write_queen_repos_config(global_bees_dir: Path, entries: list[tuple[str, bool | None]]) -> None:
    """Write queen_repos into global config.json, merging with pre-existing config.

    Loads any pre-existing config.json (e.g. written by write_scoped_config) and merges
    the queen_repos key without overwriting the scopes key. Writes the result back to
    global_bees_dir / "config.json".

    Args:
        global_bees_dir: The (mocked) global ~/.bees/ directory.
        entries: List of (path_str, write) tuples. write=None means omit the "write" key.
    """
    config_path = global_bees_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"scopes": {}, "schema_version": GLOBAL_SCHEMA_VERSION}

    queen_repos = []
    for path_str, write in entries:
        entry: dict = {"path": path_str}
        if write is not None:
            entry["write"] = write
        queen_repos.append(entry)

    config["queen_repos"] = queen_repos
    config_path.write_text(json.dumps(config, indent=2))


@pytest.fixture(autouse=True)
def guard_real_home():
    """Fail a test that resolves the home dir to, or touches bees/Claude files under, the real home."""
    problems = _home_resolution_problems()
    if problems:
        pytest.fail("\n".join(problems), pytrace=False)
    seen = len(_real_home_access)
    yield
    problems = _real_home_access[seen:] + _home_resolution_problems()
    if problems:
        pytest.fail("\n".join(problems), pytrace=False)


@pytest.fixture(autouse=True)
def mock_global_bees_dir(request, tmp_path, monkeypatch):
    """Redirect ~/.bees/ to tmp_path/global_bees/ so each test gets its own global config.

    Opt-out: @pytest.mark.needs_real_config uses the unpatched ~/.bees/, which is in the
    session's temp home (ISOLATED_HOME, shared by all such tests), never the real home.
    """
    if "needs_real_config" in request.keywords:
        # Don't mock - use the unpatched ~/.bees/ in the session's temp home
        import src.config
        src.config._SCOPE_PATTERN_CACHE.clear()
        src.config._GLOBAL_CONFIG_CACHE = None
        src.config._GLOBAL_CONFIG_CACHE_SIGNATURE = None
        src.config._IDENTITY_CACHE.clear()
        src.config._IDENTITY_CACHE_SIGNATURE.clear()
        return None

    global_bees = tmp_path / "global_bees"
    global_bees.mkdir()

    import src.config

    monkeypatch.setattr(src.config, "get_global_bees_dir", lambda: global_bees)
    monkeypatch.setattr(src.config, "get_global_config_path", lambda: global_bees / "config.json")

    # Clear the scope pattern cache to avoid stale compiled patterns
    src.config._SCOPE_PATTERN_CACHE.clear()

    # Clear the file-signature-based global config cache for test isolation
    src.config._GLOBAL_CONFIG_CACHE = None
    src.config._GLOBAL_CONFIG_CACHE_SIGNATURE = None

    # Clear the identity.json file-signature cache for test isolation
    src.config._IDENTITY_CACHE.clear()
    src.config._IDENTITY_CACHE_SIGNATURE.clear()

    # Clear any in-memory override to prevent leakage between tests
    src.config._GLOBAL_CONFIG_OVERRIDE = None

    return global_bees


@pytest.fixture(autouse=True)
def mock_git_repo_check(request, monkeypatch):
    """Patch get_repo_root_from_path to return resolved start_path directly (matches real behavior)."""
    if "needs_real_git_check" in request.keywords:
        return

    def mock_get_repo_root(start_path: Path) -> Path:
        return start_path.resolve()

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
            body: str | None = None,
            **extra_fields,
        ):
            """Create a ticket file with proper YAML frontmatter structure.

            Args:
                guid: Explicit GUID string. When None, auto-generates a valid GUID
                      from the ticket's short_id.
                body: Explicit body string. When None, defaults to the legacy
                      ``"{title} body content."`` string so existing callers are
                      unaffected (SR-10.3).
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

            # Include reference_materials: null for bee tickets so they pass linter integrity checks
            if ticket_type == "bee" and "reference_materials" not in extra_fields:
                frontmatter["reference_materials"] = None

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
            if body is None:
                yaml_lines.append(f"{title} body content.")
            else:
                yaml_lines.append(body)

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
def priority_tickets(isolated_bees_env):
    """Tickets with priorities for query tests, in one hive ("test_hive") of the isolated env.

    Four bees and four t1 children carry priorities 2, 0, -1 and unset; a fifth bee has no
    priority but the tag ``priority:1``. Returns {ticket_id: priority}, None when unset.
    ``b.pt1`` (PRIORITY_TAGGED_BEE_ID in tests.test_constants) is the tagged bee.
    """
    from tests.test_constants import PRIORITY_TAGGED_BEE_ID

    helper = isolated_bees_env
    hive_dir = helper.create_hive("test_hive", "Test Hive")
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    tickets: dict[str, int | None] = {}
    for short, priority in (("pa1", 2), ("pb1", 0), ("pc1", -1), ("pd1", None)):
        bee_id = f"b.{short}"
        extra = {} if priority is None else {"priority": priority}
        helper.create_ticket(hive_dir, bee_id, "bee", f"Bee {short}", **extra)
        child_id = f"t1.{short}.k1"
        helper.create_ticket(hive_dir / bee_id, child_id, "t1", f"Task {short}", parent=bee_id, **extra)
        tickets[bee_id] = priority
        tickets[child_id] = priority

    helper.create_ticket(hive_dir, PRIORITY_TAGGED_BEE_ID, "bee", "Tagged bee", tags=["priority:1"])
    tickets[PRIORITY_TAGGED_BEE_ID] = None
    return tickets


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


@pytest.fixture(
    scope="function",
    params=["bees_only", "two_tier", "three_tier", "four_tier"],
)
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

    tier_configs = {
        "bees_only": {},
        "two_tier": {"t1": ["Task", "Tasks"]},
        "three_tier": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
        "four_tier": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"], "t3": ["Work Item", "Work Items"]},
    }

    tier_config = tier_configs[request.param]

    # Create .hive identity marker with child_tiers and optional status_values
    hive_identity_dir = hive_path / ".hive"
    hive_identity_dir.mkdir(parents=True, exist_ok=True)
    identity_data = {
        "normalized_name": HIVE_BACKEND,
        "display_name": "Backend",
        "created_at": "2026-02-05T00:00:00",
    }
    write_identity(hive_identity_dir, identity_data)

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

        # Create .hive identity marker with child_tiers
        hive_identity_dir = hive_path / ".hive"
        hive_identity_dir.mkdir(parents=True, exist_ok=True)
        identity_data = {
            "normalized_name": hive_name,
            "display_name": hive_name.title(),
            "created_at": "2026-02-05T00:00:00",
            "child_tiers": tier_config,
        }
        write_identity(hive_identity_dir, identity_data)

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
        "hive_with_status_values",
    ],
)
def per_hive_tier_config(request, bees_repo, monkeypatch, mock_global_bees_dir):
    """
    PARAMETERIZED: Tests 5 per-hive child_tiers resolution scenarios.

    Scenarios:
        - hive_override_epics: features hive overrides scope with Epic/Task tiers
        - hive_bees_only_override: bugs hive uses empty {} to force bees-only
        - hive_inherits_scope: backend hive has no child_tiers key, inherits scope default
        - mixed_hive_tiers: multiple hives each with different tier configs
        - hive_with_status_values: features hive with explicit status_values in identity

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

    def _make_hive(name, child_tiers=None, status_values=None):
        hive_path = repo_root / name
        hive_path.mkdir(parents=True, exist_ok=True)
        hive_identity_dir = hive_path / ".hive"
        hive_identity_dir.mkdir(parents=True, exist_ok=True)
        identity_data = {"normalized_name": name, "display_name": name.title(), "created_at": "2026-02-05T00:00:00"}
        if child_tiers is not None:
            identity_data["child_tiers"] = child_tiers
        if status_values is not None:
            identity_data["status_values"] = status_values
        write_identity(hive_identity_dir, identity_data)
        return hive_path

    if request.param == "hive_override_epics":
        # features hive overrides scope with Epic/Task
        hive_paths = {HIVE_FEATURES: _make_hive(HIVE_FEATURES, child_tiers=HIVE_TIER_EPICS)}
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {HIVE_FEATURES: HIVE_TIER_EPICS}
        expected = {HIVE_FEATURES: HIVE_TIER_EPICS}

    elif request.param == "hive_bees_only_override":
        # bugs hive forces bees-only with empty {}
        hive_paths = {HIVE_BUGS: _make_hive(HIVE_BUGS, child_tiers=HIVE_TIER_BEES_ONLY)}
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {HIVE_BUGS: HIVE_TIER_BEES_ONLY}
        expected = {HIVE_BUGS: HIVE_TIER_BEES_ONLY}

    elif request.param == "hive_inherits_scope":
        # backend hive has no child_tiers key → inherits scope default
        hive_paths = {HIVE_BACKEND: _make_hive(HIVE_BACKEND)}
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {}  # no hive-level overrides
        expected = {HIVE_BACKEND: SCOPE_TIER_DEFAULT}

    elif request.param == "hive_with_status_values":
        # features hive with explicit status_values in identity
        hive_paths = {
            HIVE_FEATURES: _make_hive(
                HIVE_FEATURES,
                child_tiers=HIVE_TIER_EPICS,
                status_values=["todo", "doing", "review", "merged"],
            ),
        }
        scope_tiers = SCOPE_TIER_DEFAULT
        per_hive = {HIVE_FEATURES: HIVE_TIER_EPICS}
        expected = {HIVE_FEATURES: HIVE_TIER_EPICS}

    else:  # mixed_hive_tiers
        # features=Epic/Task, bugs=bees-only, backend=inherits scope
        hive_paths = {
            HIVE_FEATURES: _make_hive(HIVE_FEATURES, child_tiers=HIVE_TIER_EPICS),
            HIVE_BUGS: _make_hive(HIVE_BUGS, child_tiers=HIVE_TIER_BEES_ONLY),
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

    # Create .hive marker with child_tiers
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir()
    identity_data = {
        "normalized_name": "backend",
        "display_name": "Backend",
        "created_at": "2026-02-05T00:00:00",
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_identity(hive_marker, identity_data)

    # Write scoped global config
    scope_data = {
        "hives": {"backend": {"path": str(hive_dir), "display_name": "Backend", "created_at": "2026-02-05T00:00:00"}},
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

    with repo_root_context(tmp_path):
        yield tmp_path, hive_dir, "backend"


@pytest.fixture
def compat_084(tmp_path, monkeypatch, mock_global_bees_dir):
    """A registered copy of the bees-md 0.8.4 corpus (tests/fixtures/compat_0_8_4), cwd at its repo; yields its root."""
    from tests.helpers import install_compat_084

    root = tmp_path / "root"
    repo = install_compat_084(root, mock_global_bees_dir)
    monkeypatch.chdir(repo)
    with repo_root_context(repo):
        yield root


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


# ============================================================================
# LOCAL NETWORK FIXTURES (CI script tests)
# ============================================================================


class _StubHandler(BaseHTTPRequestHandler):
    """Answers from server.routes: {(method, path): (status, headers, body) | None (drop) | responder}.

    A responder is called with (lowercased headers, body) and returns one of the other two.
    """

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        headers = {key.lower(): value for key, value in self.headers.items()}
        self.server.requests.append(SimpleNamespace(method=self.command, path=self.path, headers=headers))
        route = self.server.routes.get((self.command, self.path), (404, {}, b"Not Found"))
        if callable(route):
            route = route(headers, body)
        if route is None:
            self.close_connection = True  # accept the request, then hang up without a response
            return
        status, out_headers, payload = route
        self.send_response(status)
        for key, value in out_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_DELETE = _handle

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_server():
    """Factory: start a stub HTTP server on 127.0.0.1 with an OS-assigned port; returns it with .url."""
    servers = []

    def start(routes):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        server.routes = routes
        server.requests = []
        server.url = f"http://127.0.0.1:{server.server_address[1]}"
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def closed_port_url():
    """Base URL of an OS-assigned 127.0.0.1 port that was just released, so nothing listens on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
