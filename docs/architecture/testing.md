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
- `stub_server`: Factory for a stub HTTP server on `127.0.0.1` with an OS-assigned port, answering from a routes map (CI script tests)
- `closed_port_url`: URL of a `127.0.0.1` port nothing listens on (CI script tests)

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

For CI script tests: `load_script()` imports a `docker/` script by path (`docker/` is not a package), with its `docker/` neighbours importable as in the container. `mcp_initialize_response()` builds the JSON-RPC `initialize` result of an MCP server with a given name.

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
| CI scripts and `/ci` skill | `test_check_bees_server.py`, `test_ci_bug_filing.py`, `test_ci_skill.py` | See "Integration Testing Deep Dive" |

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

### CI Phase Container

- **Test plan**: the phases run `b.qi9` from this checkout's `docker/testplans`, which `run_test.sh` mounts read-only into each phase container. `/ci` reads the same copy, from its files (see "CI Phase Status"). Neither looks the plan up among the host's registered hives: the hive registered as `testplans` there may be another checkout's copy or another repo's hive. If `docker/testplans/b.qi9/b.qi9.md` is missing, `run_test.sh` stops before the image build, a launch failure.
- **Host Claude config**: `run_test.sh` mounts the host's `~/.claude.json` and `~/.claude/settings.json` read-only, each only if it exists. For a missing file, `docker run` would create a root-owned directory at that host path. `docker/entrypoint.sh` works without them.

### CI Bug Server

`/ci` runs each phase in its own Docker container (`docker/run_test.sh`). When a test fails, the container files a bug into this repo's bugs hive, through a bees HTTP server on the host.

- **Port**: `BEES_CI_PORT`, default 8473. This is CI's own port, separate from the `bees serve --http` default of 8000, which other services on a dev host often hold. `/ci` always starts the server with an explicit `--port`, so `http.port` in the global config cannot move it.
- **URL**: containers reach the server at `http://host.docker.internal:<port>`. Every container gets the same `--add-host host.docker.internal:host-gateway` mapping. If `BEES_MCP_URL` is set, `run_test.sh` uses that URL as-is. It must include an explicit port (e.g. `http://myhost:8473`): the in-container identity check rejects a URL without one.
- **Bind host**: the server must listen where `host.docker.internal` leads. On Linux Docker Engine, that is the default bridge gateway (e.g. `172.17.0.1`), and a server bound to `127.0.0.1` is unreachable from the containers. On Docker Desktop, that is the host's loopback. `docker/ci_bind_host.py` reads `docker network inspect bridge` output and prints the bridge gateway only if it is an address of this host, otherwise `127.0.0.1`. A successful bind is no proof, because some hosts allow binding non-local addresses, so the helper binds the gateway, listens, and connects to the bound socket with a 0.5 s timeout. That connection succeeds only for an address of this host. The helper never prints `0.0.0.0`, which would expose the server on every network. It prints only the address on stdout and the reason on stderr. `/ci` starts the server with `--host <bind host>`. `bees serve --http` defaults to `127.0.0.1`. Only the CI server uses the bind host.
- **Identity check**: `docker/check_bees_server.py` sends an MCP `initialize` request and accepts only a server whose `serverInfo.name` is `bees`. A `/health` check is not enough: another service on the same port may answer it too. It runs at two points:
  - **On the host**, against the bind host, where the containers connect, not loopback. `/ci` runs it first and starts the server only if nothing listens there. `run_test.sh` runs it before the image build, so it fails fast, but only when `BEES_MCP_URL` is not set.
  - **From a container**, always, also when `BEES_MCP_URL` is set. After the build and before the phase container starts, `run_test.sh` runs the check in a throwaway `bees-test` container with the same host mapping, against `BEES_MCP_URL`. It sees exactly the server the tests will use, so this check is definitive. It also catches a host firewall that blocks container-to-host traffic. `Dockerfile.test` copies the check script into the image for this.
- **Port conflicts**: if another service holds the port at the bind host, CI stops and asks for a free port. It never stops, signals or reconfigures the other process.
- **Server lifetime**: the bees HTTP server has no authentication. On Linux Docker Engine it listens on the bridge address, so while it runs every container on this host can reach it, and possibly other hosts that route the bridge subnet to this machine. So `/ci` stops a server it started as soon as the run ends: after all phases pass, when a phase fails, when publishing to test.pypi fails, on a launch failure, and on any other early end. It records the server's PID in `/tmp/bees_ci_server.pid` and kills that PID only after `ps` shows its command line is still the `bees serve --http --host <bind host> --port <port>` it launched, since a PID may be reused. A server already running when `/ci` begins was started either by the user or by an earlier `/ci` run that was interrupted before it could stop it. `/ci` runs the same `ps` check on the PID file, without killing anything: if the recorded PID is still that `bees serve` command, `/ci` keeps the file and stops that server when this run ends. Otherwise it deletes the stale file, and a server the user started keeps running.
- **Launch failure**: `run_test.sh` exits non-zero when a pre-flight check fails (for example test plan `b.qi9` missing from this checkout's `docker/testplans`, no bugs hive found, or the in-container identity check) or the image build or container start fails. That phase never starts, so there is nothing to poll. `/ci` runs each phase launch as its own command and checks its exit status before the next launch, since one combined command reports only the last status. A launch returns once its container is up, so the phases still run in parallel. All phases share one server and image, so the failure would repeat: `/ci` shows the output, removes the containers and sessions of every phase in that launch (including any already running), marks their epics `failed` (with a status hive, see "CI Phase Status"), stops the server it started, and stops.
- **Container-internal ports** (the phase 4 HTTP server under test, the servers `tests/integration.sh` starts) are separate and do not use `BEES_CI_PORT`.
- **Bugs hive and repo root**: CI must run unmodified on any developer machine, and hive names and paths differ between machines, so no CI file has either built in. `run_test.sh` resolves both on the host, prints them in its banner, and passes them into the phase container as env vars:
  - `BEES_REPO_ROOT`: the host directory the bees server picks this repo's hives by. Default: this checkout. `run_test.sh` resolves symlinks in it, as the bees CLI does with its working directory, so the server sees the same hives the CLI lists there.
  - `BEES_BUGS_HIVE`: the hive bugs are filed into. Default: picked from `bees list-hives` run in `BEES_REPO_ROOT`. `run_test.sh` runs `bees list-hives` only for this, so only when `BEES_BUGS_HIVE` is not set. If `bees list-hives` fails, `run_test.sh` prints its output (bees reports its errors as JSON on stdout) and stops before the image build. When the rule below gives no answer, it stops there too. Both are launch failures.
  - Setting either env var on the host overrides it.
- **Bugs hive rule**: `docker/ci_bugs_hive.py` holds it, for `run_test.sh` and `file_bug.py` alike (`ci_plan.py` imports its scope matching and ranking too), and needs the repo root the hives were listed for (`--repo-root` on its command line). bees lists more than this repo's own hives: also those of the less specific scopes above the repo's own scope, and for a queen repo those of every scope. So the rule goes by the scope each entry names, and skips entries without a normalized name and a scope:
  - Only scopes whose pattern matches the repo root count, as bees matches them, wildcards anywhere in the pattern included. They go most specific first, ranked as bees ranks them: more path segments first (wildcard segments count too), then an exact path before a terminal `/*` before a terminal `/**`.
  - Within a scope, the candidates are the hive whose normalized name is `bugs`, else every hive whose name contains `bugs` (both case-insensitive).
  - The most specific scope that has candidates decides. One candidate is the answer. Several candidates there, or candidates in two equally specific scopes, is no answer; a less specific scope is never tried instead. No candidate in any matching scope is no answer too, and the reason names any bugs hives of non-matching scopes.
  - `ci_bugs_hive.py` is stdlib-only, since it runs on the host with plain `python3`, so it copies bees' scope matching (the pattern-to-regex rule of `match_scope_pattern`) and `compute_scope_specificity` from `src/config.py` instead of importing them, unchanged in behavior. `colonize-hive` writes only an exact path or a terminal `/*` or `/**`, but bees matches whatever a hand-written config holds, wildcards anywhere (e.g. `/x/bees*`, `/x/*/bees`, `/x/**/`), so the copy does too. `test_scope_rule_agrees_with_bees` checks the copy against bees' own functions, on such patterns and trailing slashes: change both together.
- **Filing a bug**: `docker/file_bug.py` files the bug in the container. It takes the hive from `--hive`, else `BEES_BUGS_HIVE`, else asks the server (`list_hives` for the repo root, then the `ci_bugs_hive.py` rule; `Dockerfile.test` copies that script next to `file_bug.py` for the import). It takes the repo root from `--repo-root`, else `BEES_REPO_ROOT`. There is no default path: without one it fails. The whole exchange with the server (connect, initialize, `list_hives`, `create_ticket`) gets 60 s (`FILE_BUG_TIMEOUT_SECONDS`), so a server that accepts the connection but never answers cannot hold the phase until `/ci`'s phase deadline. The limit also covers closing the MCP session. It prints `BUG FILED: <id>` on success. Every failure (no repo root, no bugs hive, ticket rejected, server unreachable, not answering in JSON, or no answer within the limit) prints `BUG FILING FAILED: <reason>` and exits 1, so a failed filing still ends in a line `/ci` polls for.

`tests/test_check_bees_server.py` holds the unit tests for the identity check, the bind host choice, and the host-address proof (`local_address_error`). It also holds static checks of the CI scripts: the shared default port, the checks at the bind host, the in-container check between build and phase (a failed check stops `run_test.sh`), and the `/ci` skill stopping only a server a `/ci` run started, guarded by the command-line check, on every path that ends the run, and launching each phase as its own command. Further static checks cover portability and monitoring: no user home directory or Homebrew path in the CI scripts and skills, `run_test.sh` passing `BEES_BUGS_HIVE` and `BEES_REPO_ROOT` into the phase container and stopping before the build when no bugs hive is found, `run_test.sh` mounting this checkout's `docker/testplans` (which must hold `b.qi9`) and running `bees list-hives` only when `BEES_BUGS_HIVE` is not set, `run_test.sh` printing the `bees list-hives` output when that command fails, `run_test.sh` mounting the host's Claude config files only if they exist, `Dockerfile.test` installing the `docker/` modules `file_bug.py` imports next to it, every `/ci` poll checking the phase deadline, and every signal `/ci` polls for being printed by a CI script. Tests that need a local stand-in for the bridge gateway use `127.0.0.2`. Tests of a host that allows non-local binding set `IP_FREEBIND` on the helper's sockets. Both run on Linux only.

`tests/test_ci_bug_filing.py` tests the bugs hive rule and `file_bug.py`. For the rule: `choose_bugs_hive` on the candidates within a scope and on which scope wins (own scope over inherited ones, ranking, ties, a queen repo's non-matching scopes), `test_scope_rule_agrees_with_bees` (matching and `compute_scope_specificity`, for exact paths, terminal `/*` and `/**`, wildcards anywhere and trailing slashes), and the `ci_bugs_hive.py` command line on real `bees list-hives` output across scopes and for a queen repo. For `file_bug.py`: the order in which it takes the hive and the repo root, the ticket it files, and the `BUG FILING FAILED:` line and exit 1 on each failure, including an unreachable server and a server that opens the session and then stops answering (given up at the time limit). It runs `file_bug.py` against the real bees MCP server in-process, with the hives in `tmp_path`, and the time limit test against a `stub_server`. No hive in its `file_bug.py` tests is named `bugs` (they use names like `team_bugs`, `triage` and `features`), so discovery passes only by the rule, never by a built-in name.

### CI Phase Monitoring

`/ci` reads each phase's result from its tmux pane. It uses the container state only to detect a crash (the container is no longer running).

- **Containers stay up**: in every phase, including the bash phases, the container's tmux session stays open after the test runner exits, with its last output on screen, until `/ci` removes the container. A running container says nothing about progress.
- **Signals**: the results are `RELEASE TEST PHASE N PASSED` and `BUG FILED:`. `/ci` checks them first, because a crash signal can print below a result. The crash signals are `BUG FILING FAILED:` (from `file_bug.py`), `TEST RUNNER EXITED (status N)` (printed by `docker/entrypoint.sh` when the test runner ends), and `--- Phase N exited` (printed by the host tmux session `run_test.sh` creates when it loses the container's session, for example because the container stopped).
- **Phase timeout**: `BEES_CI_PHASE_TIMEOUT_MINUTES`, default 60. `/ci` checks that it is a whole number greater than 0 before anything starts. Each phase's deadline is set when its launch returns. A phase with no signal by its deadline is handled as crashed, so a phase that never reports cannot hang `/ci`.
- **Crash report**: `/ci` names the cause: the bug could not be filed (with the reason from the `BUG FILING FAILED:` line), the phase timed out, or it crashed.

### CI Phase Status

With a status hive (below), `/ci` records each phase's result as the status of its epic under b.qi9: `pupa` (to run), `worker` (running), `finished` (passed), `failed` (bug filed or crashed), and `legendary` (set on every epic once all phases pass). A plain `/ci` skips `finished` and `legendary` epics, unless every epic has one of those statuses; then it starts a fresh run. `/ci full` runs every phase. `/ci <test number>` starts at that test's phase: the phases before it do not run, and with a status hive they are marked `finished`.

- **Reading the plan**: `/ci` runs `bees list-hives | python3 docker/ci_plan.py` from the checkout root. `docker/ci_plan.py` reads `b.qi9` from this checkout's `docker/testplans` files, the copy the containers run, and prints JSON: the phases in the plan's `children` order (1st child is Phase 1), each with its epic's ID, title and status, then `status_hive` and `status_hive_reason`. It exits 1 only when it cannot read the plan; `/ci` then stops. The skill never reads or writes the plan through the bees MCP tools: the host's `testplans` hive may be another copy (in a worktree, usually the main checkout's). It finds a test number's phase in the same files: the epic whose directory holds a test titled `Test <N>:`, else the epic whose body gives a `Tests in this phase:` range that holds the number.
- **Phase order**: `/ci` runs every phase `ci_plan.py` lists that is in the run scope, however many the plan has. Phase 1, the plan's first child, is the gatekeeper: when it is in the run scope, it runs alone, and the other phases start only if it passes. Then every other phase in the run scope launches in parallel, each with its own container, tmux session `bees-ci-<N>` and deadline.
- **Status hive**: the hive `/ci` writes statuses through, matched by path, never by name. Of the hives `bees list-hives` lists, `ci_plan.py` takes those in scopes matching the repo root and, for each name, the most specific scope's definition, as bees resolves a name there. The status hive is the one whose path, symlinks resolved, is this checkout's `docker/testplans`. A name that two equally specific scopes give different paths does not count, since which one bees uses is not certain, and neither does a hive with a relative path. If `bees list-hives` fails, there is no status hive, and the reason relays bees' error. Scope matching and ranking come from `ci_bugs_hive.py`.
- **With a status hive**: each status change is `bees update-ticket --ids <epic IDs> --status <status> --hive <status_hive>`, run from the checkout root. A failed write is reported and the run continues: a status is a record, not a test result.
- **Without one**: `/ci` records nothing. It runs every phase, as with `full`, since no run could update the statuses it would skip by, and tells the user once: "Phase statuses will not be recorded: <reason>. Running all phases." A test number still skips the phases before its phase.
- **Limitation**: in a worktree whose `docker/testplans` is not registered as a hive bees resolves there, `/ci` cannot resume: no statuses are recorded, so every run starts again at Phase 1, or at the given test's phase.
- **Stdlib only**: `ci_plan.py` runs on the host with plain `python3`, so it reads ticket frontmatter itself, not with PyYAML. It reads only what the plan's fields need, as bees writes them: plain, quoted and null scalars, block lists, and values wrapped onto a second line.

The testplans hive rejects any status not listed in `status_values` in `docker/testplans/.hive/identity.json`, so the skill and that file must agree. If you add a status to the skill, add it there too.

`tests/test_ci_skill.py` tests `ci_plan.py`: the phases in `children` order, plans it cannot read, frontmatter read as PyYAML reads it (bees' own writer output included), and its command line, with and without a hive list. The status hive tests cover this copy under any name or through a symlink, another copy only, the most specific scope winning or shadowing, equally specific scopes, a queen repo's non-matching scopes, a glob scope and a relative path; for each hive picked, they check that bees resolves that name for the repo root to this copy. Static checks on the skill: it pipes `bees list-hives` into `ci_plan.py`, it never names `show_ticket`, `update_ticket` or `bees show-ticket`, every `update-ticket` command has `--status` and `--hive`, every status the skill sets or reads is allowed, and its commands name no phase number but Phase 1, the gatekeeper (every later phase is launched and polled through a `<N>` placeholder; any number in a `run_test.sh` phase argument or a `bees-ci-` session name counts as a fixed phase). A static check on the release-test skill: it gives no list or range of phase numbers (such as `1, 2, 3, or 4`, `3/4`, `1-4`, `2 through 6` or `Phase 3 and Phase 4`).

## Bash Integration Test Script

In CI, `docker/test_runner.sh` runs Phases 1, 2 and 5 of the integration test suite with a standalone bash script (`tests/integration.sh`). These phases exercise the installation and the CLI end-to-end — hive management, ticket CRUD, queries, dependencies, reference materials resolvers, and more — without requiring an API token or LLM session. They are fast, deterministic, and safe to run on every change.

For every other phase, it launches Claude with `/release-test`. This routing may change. Phases 3 and 4 validate the full LLM-agent interaction loop against a live MCP server (stdio and HTTP), catching interaction-level bugs that bash cannot. The split gives developers rapid feedback locally while reserving token spend for the tests that genuinely need it.

### Prerequisites

- `bees` installed — either via the dev path (`poetry install -E serve`) or the user path (`pipx install bees-md[serve]`)
- A writable working directory (the script creates hives, tickets, and config during execution)
- No pre-existing `~/.bees/config.json` — the script overwrites global config and is destructive to any existing setup. Back up or remove the file before running.
- Claude-run phases only: a Claude Code session with a configured MCP server

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
