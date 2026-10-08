# Test Architecture

Unit tests: 
- Pytest with tiered fixtures for test isolation and hive-based architecture validation.
- Real filesystem operations over mocking.

Integration tests:
- In a Bee in the Testplans hive called b.qi9
- Use for high level end-to-end test of an actual instance of Bees, used by an LLM
- Use Plain English, do not list bees commands
- Try to write tests that can be run in isolation
- If you must write tests that depend on previous tests, ensure the ticket dependencies represent this

## Unit Testing Deep Dive

**Full fixture docs**: `tests/TESTING.md` (fixture reference, mock patching strategy, decision tree, code examples).

### Core Principles

1. **Test behavior, not implementation** - Focus on outputs, not internals
2. **Integration over isolation** - Bees is filesystem-based; real operations catch real bugs
3. **Parametrize over duplication** - 3+ similar tests → `@pytest.mark.parametrize`
4. **DRY with fixtures and factories** - No copy-paste setup
5. **No meta-tests** - Don't test fixtures/helpers; real tests validate them
6. **Coverage through cases, not count** - 10 parametrized tests > 50 same-path tests

### Standards

- **Coverage**: ≥85% overall, ≥70% per-file. Simple functions get 4-5 test cases max.
- **File size**: Max 1,600 lines per test file. Split by feature area if larger.
- **Test-to-source ratio**: Target 2.0-2.5:1 (currently ~2.3:1)
- **Prefer integration tests** over heavy mocking. Mocking hides path resolution and file I/O bugs.

**Don't bother covering**: error message exact text, internal helpers only called by tested code, framework features (dict.get(), Path.exists()).

### Fixtures Summary

#### Autouse (always active)
- `backup_global_config`: Backs up/restores `~/.bees/config.json` (session-scoped)
- `mock_global_bees_dir`: Redirects `~/.bees/` to `tmp_path/global_bees/` for isolation
- `mock_git_repo_check`: Mocks git repo validation (opt-out: `@pytest.mark.needs_real_git_check`)
- `set_repo_root_context`: Sets repo context to `Path.cwd()` (opt-out: `@pytest.mark.no_repo_context`)

#### Opt-in
- `mock_mcp_context`: Factory for mock MCP Context objects
- `isolated_bees_env`: Full environment with BeesTestHelper

### Parameterized
- `hive_tier_config`: 4 tier configs (bees-only, 2-tier, 3-tier, 4-tier)
- `multi_hive_config`: 3 multi-hive scenarios (isolated, connected, mixed)
- `ticket_hierarchy`: 5 ticket structures (single, parent-child, hierarchy, siblings, deps)

#### Choosing fixtures
| Scenario | Fixture |
|----------|---------|
| MCP tool function | `mock_mcp_context` |
| Core function | `tmp_path + monkeypatch.chdir` |
| Test across tier configs | `hive_tier_config` |
| Test multi-hive scenarios | `multi_hive_config` |
| Test with existing tickets | `ticket_hierarchy` |
| Complex integration | `isolated_bees_env` |

### Data Factories (helpers.py)

```python
from tests.helpers import make_ticket, write_ticket_file

ticket = make_ticket(title="Test", status="open")  # sensible defaults
write_ticket_file(hive_path, ticket)                # handles YAML frontmatter + file naming
```

Also available: `setup_child_tiers()`, `assert_ticket_id_format()`, `assert_relationship_bidirectional()`, `build_test_scenario()`.

### Parametrization

When 3+ tests follow the same structure, parametrize:

```python
@pytest.mark.parametrize("field,value", [
    pytest.param("title", "Test", id="with_title"),
    pytest.param("body", "Body text", id="with_body"),
    pytest.param("tags", ["test"], id="with_tags"),
])
def test_create_bee_with_optional_fields(field, value):
    ...
```

Always use descriptive `id=` strings for clear failure messages.

### Mock Patching

**Golden Rule**: Patch where functions are **used**, not where defined.
- ✅ `@patch('module_using_it.shutil.rmtree')`
- ❌ `@patch('shutil.rmtree')`

Minimize mocking: use real filesystem with `tmp_path`. If mocking > 3 things, write an integration test instead.

## Constants

Create constants for complex formats used in 5+ places. Inline simple strings like `"open"`, `"completed"`, `"bee"`. Run `ruff check tests/ --select F401` to catch unused imports.

### Test Placement

**Always read the target file's module docstring before adding tests** - docstrings are the authoritative scope source.

| Scenario | File |
|----------|------|
| Core creation logic, validation, relationships | `test_create_ticket.py` |
| N-tier creation chains (bee→t1→t2→t3) | `test_tier_hierarchy_validation.py` |
| Single ticket tier rules ("can t1 have bee parent?") | `test_create_ticket.py` |
| Multi-tier edge cases (3-tier, 4-tier systems) | `test_tier_hierarchy_validation.py` |

**Before adding a test**: search for similar scenarios in existing files. Prefer adding to existing files over creating new ones.

## Key Test Suites

| Area | Files | Notes |
|------|-------|-------|
| Hive management | `test_colonize_hive.py`, `test_mcp_rename_hive.py`, `test_hive_utils.py` | |
| Ticket lifecycle | `test_create_ticket.py`, `test_ticket_factory.py`, `test_delete_ticket.py` | |
| Path & ID | `test_paths.py`, `test_id_utils.py` | |
| Config | `test_config.py`, `test_config_registration.py` | |
| Queries | `test_query_tools.py`, `test_multi_hive_query.py`, `test_graph_executor.py` | |
| MCP server | `test_mcp_server.py` (~1600 lines), `test_mcp_server_lifecycle.py`, `test_mcp_scan_validate.py` | |
| Dynamic tiers | `test_tier_hierarchy_validation.py`, `test_dynamic_tier_validation.py`, `test_parent_requirement_logic.py` | |

**Current**: ~1,578 tests across ~64 files.

### Test Execution

```bash
poetry run pytest tests/ -v                              # all tests
poetry run pytest tests/test_create_ticket.py -v         # specific file
poetry run pytest tests/ --cov=src --cov-report=term-missing  # with coverage
```

## Integration Testing Deep Dive
Integration tests are describe in plain English in a Bee in the Testplans hive called b.qi9.
There is a t1 level ticket for each area of testing. These are executed as a group in a docker container.
Each testcase is a t2 level ticket under those t1s.
Add new t2 tickets if needed based on the changes. Modify or remove existing t2 tickets if needed, as well.
Use for high level end-to-end test of an actual instance of Bees, used by an LLM
Use Plain English, do not list bees commands
Try to write tests that can be run in isolation
If you must write tests that depend on previous tests, ensure the ticket dependencies represent this

### CI Bug Server

`/ci` runs each phase in its own Docker container (`docker/run_test.sh`). When a test fails, the container files a bug against a bees HTTP server on the host.

- **Port**: `BEES_CI_PORT`, default 8473. This is CI's own port, separate from the `bees serve --http` default of 8000, which other services on a dev host often hold. `/ci` always starts the server with an explicit `--port`, so `http.port` in the global config cannot move it.
- **URL**: containers reach the server at `http://host.docker.internal:<port>`. Every container gets the same `--add-host host.docker.internal:host-gateway` mapping. If `BEES_MCP_URL` is set, `run_test.sh` uses that URL as-is. It must include an explicit port (e.g. `http://myhost:8473`): the in-container identity check rejects a URL without one.
- **Bind host**: the server must listen where `host.docker.internal` leads. On Linux Docker Engine, that is the default bridge gateway (e.g. `172.17.0.1`), and a server bound to `127.0.0.1` is unreachable from the containers. On Docker Desktop, that is the host's loopback. `docker/ci_bind_host.py` reads `docker network inspect bridge` output and prints the bridge gateway only if it is an address of this host, otherwise `127.0.0.1`. A successful bind is no proof, because some hosts allow binding non-local addresses, so the helper binds the gateway, listens, and connects to the bound socket with a 0.5 s timeout. That connection succeeds only for an address of this host. The helper never prints `0.0.0.0`, which would expose the server on every network. It prints only the address on stdout and the reason on stderr. `/ci` starts the server with `--host <bind host>`. `bees serve --http` defaults to `127.0.0.1`. Only the CI server uses the bind host.
- **Identity check**: `docker/check_bees_server.py` sends an MCP `initialize` request and accepts only a server whose `serverInfo.name` is `bees`. A `/health` check is not enough: another service on the same port may answer it too. It runs at two points:
  - **On the host**, against the bind host, where the containers connect, not loopback. `/ci` runs it first and starts the server only if nothing listens there. `run_test.sh` runs it before the image build, so it fails fast, but only when `BEES_MCP_URL` is not set.
  - **From a container**, always, also when `BEES_MCP_URL` is set. After the build and before the phase container starts, `run_test.sh` runs the check in a throwaway `bees-test` container with the same host mapping, against `BEES_MCP_URL`. It sees exactly the server the tests will use, so this check is definitive. It also catches a host firewall that blocks container-to-host traffic. `Dockerfile.test` copies the check script into the image for this.
- **Port conflicts**: if another service holds the port at the bind host, CI stops and asks for a free port. It never stops, signals or reconfigures the other process.
- **Server lifetime**: the bees HTTP server has no authentication. On Linux Docker Engine it listens on the bridge address, so while it runs every container on this host can reach it, and possibly other hosts that route the bridge subnet to this machine. So `/ci` stops a server it started as soon as the run ends: after all phases pass, when a phase fails, when publishing to test.pypi fails, on a launch failure, and on any other early end. It records the server's PID in `/tmp/bees_ci_server.pid` and kills that PID only after `ps` shows its command line is still the `bees serve --http --host <bind host> --port <port>` it launched, since a PID may be reused. A server already running when `/ci` begins was started either by the user or by an earlier `/ci` run that was interrupted before it could stop it. `/ci` runs the same `ps` check on the PID file, without killing anything: if the recorded PID is still that `bees serve` command, `/ci` keeps the file and stops that server when this run ends. Otherwise it deletes the stale file, and a server the user started keeps running.
- **Launch failure**: `run_test.sh` exits non-zero when a pre-flight check fails (for example the in-container identity check) or the image build or container start fails. That phase never starts, so there is nothing to poll. `/ci` runs each phase launch as its own command and checks its exit status before the next launch, since one combined command reports only the last status. A launch returns once its container is up, so the phases still run in parallel. All phases share one server and image, so the failure would repeat: `/ci` shows the output, removes the containers and sessions of every phase in that launch (including any already running), marks their epics `failed`, stops the server it started, and stops.
- **Container-internal ports** (the phase 4 HTTP server under test, the servers `tests/integration.sh` starts) are separate and do not use `BEES_CI_PORT`.

`tests/test_check_bees_server.py` holds the unit tests for the identity check, the bind host choice, and the host-address proof (`local_address_error`). It also holds static checks of the CI scripts: the shared default port, the checks at the bind host, the in-container check between build and phase (a failed check stops `run_test.sh`), and the `/ci` skill stopping only a server a `/ci` run started, guarded by the command-line check, on every path that ends the run, and launching each phase as its own command. Tests that need a local stand-in for the bridge gateway use `127.0.0.2`. Tests of a host that allows non-local binding set `IP_FREEBIND` on the helper's sockets. Both run on Linux only.

### CI Phase Status

`/ci` records each phase's result as the status of its epic under b.qi9: `pupa` (to run), `worker` (running), `finished` (passed), `failed` (bug filed or crashed), and `legendary` (set on every epic once all phases pass). A plain `/ci` skips `finished` and `legendary` epics, unless every epic has one of those statuses; then it starts a fresh run.

The testplans hive rejects any status not listed in `status_values` in `docker/testplans/.hive/identity.json`, so the skill and that file must agree. If you add a status to the skill, add it there too. `tests/test_ci_skill.py` checks that every status the skill sets or reads is allowed.

## Bash Integration Test Script

Phases 1 and 2 of the integration test suite run as a standalone bash script (`tests/integration.sh`). These phases exercise the CLI end-to-end — hive management, ticket CRUD, queries, dependencies, reference materials resolvers, and more — without requiring an API token or LLM session. They are fast, deterministic, and safe to run on every change.

Phases 3 and 4 remain Claude-run. They validate the full LLM-agent interaction loop against a live MCP server, catching interaction-level bugs that bash cannot. The split gives developers rapid feedback locally while reserving token spend for the tests that genuinely need it.

### Prerequisites

- `bees` installed — either via the dev path (`poetry install -E serve`) or the user path (`pipx install bees-md[serve]`)
- A writable working directory (the script creates hives, tickets, and config during execution)
- No pre-existing `~/.bees/config.json` — the script overwrites global config and is destructive to any existing setup. Back up or remove the file before running.
- Phases 3 and 4 only: a Claude Code session with a configured MCP server

### Running Locally

All tests:

```bash
bash tests/integration.sh
```

Resume from a specific test number:

```bash
bash tests/integration.sh <test_number>
```

For a clean run, remove or back up your global config first:

```bash
mv ~/.bees/config.json ~/.bees/config.json.bak
bash tests/integration.sh
```

## Checklist for New Tests

1. Can I parametrize instead of writing N separate tests?
2. Can I use a shared fixture instead of copy-paste setup?
3. Am I testing behavior or implementation?
4. Does this constant wrap a simple string? (inline it)
5. Is this a meta-test? (delete it)
6. Did I read the target file's docstring?
7. Is a similar test already written?
8. Have you added some tests to the Integration test bee?
