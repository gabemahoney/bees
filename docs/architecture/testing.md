# Test Architecture

Unit tests: 
- Pytest with tiered fixtures for test isolation and hive-based architecture validation.
- Real filesystem operations over mocking.

Integration tests:
- In a Bee in the Testplans hive called b.qi9
- Run only in Docker: through `/ci`, or for one phase, `docker/run_test.sh <phase>`; never through `tests/integration.sh` on a host (see [Running the Integration Suite](#running-the-integration-suite)). A new machine needs the [CI prerequisites](#ci-prerequisites) first
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
5. **No meta-tests** - Don't test fixtures/helpers; real tests validate them. Exception: the real-home isolation guard tests (`TestRealHomeIsolation` in `tests/test_conftest.py`), since a broken guard fails no other test
6. **Coverage through cases, not count** - 10 parametrized tests > 50 same-path tests

### Standards

- **Coverage**: ≥85% overall, ≥70% per-file. Simple functions get 4-5 test cases max.
- **File size**: Max 1,600 lines per test file. Split by feature area if larger.
- **Test-to-source ratio**: Target 2.0-2.5:1 (currently ~2.3:1)
- **Prefer integration tests** over heavy mocking. Mocking hides path resolution and file I/O bugs.

**Don't bother covering**: error message exact text, internal helpers only called by tested code, framework features (dict.get(), Path.exists()).

### Fixtures Summary

#### Session temp home (always active)
`tests/conftest.py` points `HOME` at a temp dir for the whole session, so tests never read or write the real `~/.bees/` or `~/.claude/`, and a guard fails any test or run that touches them. Details: `guard_real_home` in `tests/TESTING.md`.

#### Autouse (always active)
- `guard_real_home`: Fails a test if `Path.home()`, `~` or the unpatched `get_global_bees_dir()` resolves into the real home, or if the guard recorded real-home access during the test
- `mock_global_bees_dir`: Redirects `~/.bees/` to `tmp_path/global_bees/`, a global config per test (opt-out: `@pytest.mark.needs_real_config` uses the unpatched `~/.bees/`, which is in the session temp home and shared by all such tests, never the real one)
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

`backdate(*paths)` sets each file's atime and mtime to one stamp a minute in the past and returns that stamp (ns). The ticket, global config, and identity caches re-read a file modified within the last 3 seconds on every lookup (see [caching.md](caching.md#freshness-check)), so a test that expects a cache hit right after writing a file must backdate the file first.

`tree_snapshot(root)` maps every file (its bytes) and directory below `root`, hidden ones included, by relative path; compare two snapshots to assert that a refused operation changed nothing on disk.

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
| Hive management | `test_colonize_hive.py`, `test_mcp_adapter.py`, `test_mcp_rename_hive.py`, `test_hive_utils.py` | `test_mcp_adapter.py` `TestColonizeHiveAdapterRepoRoot`: the `colonize_hive` adapter passes on the roots root, else the `repo_root` parameter (also when `list_roots()` raises an unexpected error rather than the `McpError` of a client without roots support), when the hive path lies inside it, and the hive path itself when the hive lies outside it or neither gives a root; without an MCP context it passes `repo_root` if given, else the hive path. `test_mcp_rename_hive.py` `TestRenameHiveNestedHive`: renaming a hive whose folder holds another hive (`.hive/` in a ticket directory, or a registered hive inside the folder) with folder rename is a `nested_hive` error naming that hive, with the folder tree and config unchanged; with `rename_folder=False`, or when the folder already has the new normalized name, it succeeds in place and the nested hive keeps its files and registration |
| Ticket lifecycle | `test_create_ticket.py`, `test_ticket_factory.py`, `test_delete_ticket.py` | `test_delete_ticket.py` `TestDeleteTicketNestedHive`: deleting a ticket whose directory holds another hive, or lies inside one, is a `delete_failed` error naming that hive with no file changed and, with `delete_with_dependencies` on, no dependency cleaned; in a bulk delete it is listed in `failed` and the other ticket is deleted |
| Move and archive | `test_move_bee.py`, `test_undertaker.py` | `test_move_bee.py`: a bee whose directory holds another hive is in `failed` naming that hive, its tree unchanged, while the other bee moves. `test_undertaker.py`: when a bee's directory holds another hive, or its `/cemetery` target is, lies in or holds one, the run is an error naming that hive and nothing is created or moved, not even a bee checked earlier; so is a bee whose `/cemetery` target already exists (an earlier archived bee with the same plain ID name, a file or a dangling symlink), the error naming that target; a target that appears after that check is refused at that bee's move, which leaves the bee in the hive and does not nest it inside the target; a bee reusing the ID of an earlier bee archived under its GUID is archived under its own GUID, the earlier bee unchanged |
| Ticket body input | `test_body_file_verbatim.py`, `test_reader.py`, `test_mcp_body_file.py`, `test_cli_read_body_file_arg.py`, `test_cli_append_ticket_body.py`, `test_cli_body_cap_on_create_update.py` | `test_body_file_verbatim.py`: file-sourced body/chunk (CLI file and stdin, MCP file; create, update, append) round-trips exactly, except CR line endings, which read back as `\n`: literal backslash sequences, leading whitespace and trailing newlines are kept, and two appended chunks that end in a newline each stay on their own line; inline body/chunk still expands literal `\n` / `\t`, a trailing one included. `test_reader.py`: a body written by `write_ticket_file` reads back unchanged, whitespace included, except CR line endings, which read back as `\n`: `test_cr_line_endings_read_back_as_lf` pins that `\r\n` and a lone `\r` become `\n` and a `\r` that ends the body is dropped; hand-written layouts (no blank line after the closing `---`, no final newline) read without that separator and final newline |
| Path & ID | `test_paths.py`, `test_id_utils.py` | `test_paths.py` `TestNestedHivePruning`: `walk_hive`, `iter_ticket_files`, `iter_ticket_files_deep` and `find_ticket_file` (strict and deep) never enter a nested hive, whether marked by `.hive/`, registered in the same scope, or registered in another scope, also when the outer hive is walked through a symlink; a walk from the nested hive's root finds its own tickets; `find_enclosing_hive_root` returns the nested root for a path inside it, else `None`; `find_nested_hive_root` returns a nested root strictly below the directory, else `None`, and finds one also under hidden directories, `evicted/` and `cemetery/`; `hive_crossing_reason` names the path and the other hive's root when the source, then the target, lies inside another hive, the source holds one (move and delete wording) or an existing target holds one, and returns `None` for a clean move or delete |
| Linter and sanitize | `test_linter.py`, `test_linter_directory_enforcement.py`, `test_linter_cycles.py`, `test_sanitize_hive.py` | `test_sanitize_hive.py`: sanitizing a hive with another hive nested in its directory (registered with and without `.hive/`, or marked only by `.hive/`) leaves the nested hive's files byte-identical and reports no errors or fixes for it; empty-directory cleanup keeps the nested hive's directories; directory enforcement reports `cross_hive_move_blocked` instead of moving across the boundary, onto a directory that is or holds another hive, or carrying a nested hive along (bee and child), and still makes an ordinary move in the same run. Each auto-fix (`add_child`, `add_down_dependency`, `add_up_dependency`, `add_guid`, `remove_dangling_dependency`, `clear_dangling_parent`) is in `fixes_applied` and on disk when written, and is a `fix_not_applied` error with the file unchanged when the write fails; once a ticket's write fails, its later fixes in the run are withdrawn too and the next run writes them all; a fix to a misplaced ticket lands in its only copy. `test_linter_directory_enforcement.py` `TestEnforceDirectoryStructureExistingTarget`: a bee or child misplaced inside its own expected directory (directly, below a subdirectory, or with a child of its own), run through `_sanitize_hive()`, ends up in its expected directory byte-identical with every other file kept and no temporary or emptied directory left; a parent misplaced inside its child's directory (bee in t1, bee in t1 in t2), given children first, still moves first and every ticket lands in place in one run; a parent cycle still ends with every ticket file kept; a move onto an existing expected directory merges into it, keeping the child and file already there; a move whose target holds a same-named entry, is a file or a symlink, or lies inside the ticket's own directory is a `move_target_conflict` error with no file changed; a name taken in the target after the conflict check (file, directory or dangling symlink; plain merge or via the temporary directory) is a `directory_enforcement_failed` error and is not overwritten or nested into; a move through the temporary directory failing at any step is a `directory_enforcement_failed` error that loses no file, removes only empty directories, and a rerun settles the tickets; a failure to remove the temporary directory does not replace the move's own error |
| Config | `test_config.py`, `test_config_registration.py` | |
| Queries | `test_query_tools.py`, `test_multi_hive_query.py`, `test_graph_executor.py`, `test_query_help.py` | `test_query_help.py`: the `execute-freeform-query` and `add-named-query` CLI help, `bees sting`, and the MCP `execute_freeform_query` / `add_named_query` descriptions each list exactly the reportable and non-reportable fields from `src/query_parser.py`, show both example queries, and contain no literal `\n`; every query example in the CLI help and `sting` output, tokenized as a shell would, runs as written against an isolated hive; the doubled-backslash regex example in the `execute-freeform-query` help and MCP `execute_freeform_query` description matches only the literal-bracket title on an isolated hive; the undertaker `query_yaml` examples (MCP `undertaker` description, `src/mcp_undertaker.py` module docstring) parse |
| MCP server | `test_mcp_server.py` (~1600 lines), `test_mcp_server_lifecycle.py`, `test_mcp_scan_validate.py` | |
| Integration test docs | `test_integration_docs.py` | Static, text-only checks of the docs; it never runs a script. No developer doc (`README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `docs/**/*.md`, `tests/TESTING.md`, the `/ci` skill) gives a shell command that runs `tests/integration.sh`, in fenced code blocks (backslash-continued lines joined) or inline code spans; prose, an inline span that only names the script, or `bash -n` (parse only) is fine. The `## CI prerequisites` section below names every home file and credential env var that `docker/run_test.sh` and `docker/publish_test_pypi.sh` read (found by parsing the scripts) and how to get the tokens, lists the tools CI runs in its `### Tools` table (first column), and names no machine-specific path (`/home/`, `/Users/`); `CONTRIBUTING.md` links to it |
| Doc examples | `test_docs_cli_examples.py` | Every `bees <subcommand> ...` command in `README.md` and `docs/**/*.md`, in fenced code blocks (backslash-continued lines joined) and inline code spans, parses as written against the parser `src/cli.py` builds: real subcommand and flags, required flags present, no abbreviated flags, valid JSON and choice values (`<placeholder>` and METAVAR words stand for any value; `[optional]` synopsis groups count as given; an inline span that only names a command need not parse). CLI references, which omit metavars, are checked only for a real subcommand and real flags, not fully parsed: rows of a markdown table with a column headed command or CLI (that column's code span plus the code spans of any argument, flag or option column), `usage: bees ...` lines (wrapped lines joined; a `{a,b}` subcommand list must name real subcommands) and bold `**bees ...**` synopses. Guards fail the test if extraction finds no command in `README.md` or `docs/advanced-usage.md`, no fenced command in `docs/advanced-usage.md`, no table, usage or bold reference, or no table reference with a flag. The wrong commands and references the docs used to show are rejected and their fixes accepted. Each PRD Appendix E tool exists, lists only its real MCP parameters, and lists every required one; the `undertaker(...)` calls in the `src/mcp_undertaker.py` module docstring pass only real parameters |
| Dynamic tiers | `test_tier_hierarchy_validation.py`, `test_dynamic_tier_validation.py`, `test_parent_requirement_logic.py` | |
| CI scripts and `/ci` skill | `test_check_bees_server.py`, `test_ci_bug_filing.py`, `test_ci_skill.py`, `test_integration_phases.py`, `test_ci_claude_stream.py` | See "Integration Testing Deep Dive" |
| Packaging | `test_package_entry_point.py` | `bees` entry point; `serve` extra caps fastmcp and mcp below their next major and matches the Poetry pins |
| Test isolation | `test_conftest.py` | `TestRealHomeIsolation`: runs an inner pytest session on this conftest with `HOME` set to a stand-in real home. A concurrent change to its `~/.bees/config.json` is kept; a write into it (swallowed, at import, or relative to a cwd in that home) is blocked and fails the run, keeping a worse exit status; a leaked `HOME` fails the test; child processes keep the original user base; the temp home is deleted, also after `pytest --version` |

**Current**: ~3,340 tests across 80 files.

### Test Execution

```bash
poetry run pytest tests/ -v                              # all tests
poetry run pytest tests/test_create_ticket.py -v         # specific file
poetry run pytest tests/ --cov=src --cov-report=term-missing  # with coverage
```

## Integration Testing Deep Dive
Integration tests are describe in plain English in a Bee in the Testplans hive called b.qi9.
There is a t1 level ticket for each area of testing. These are executed as a group in a docker container.
In a script phase, the t2 level tickets under those t1s (and any t3s under them) describe the tests of `tests/integration.sh`.
In a Claude phase, each t2 is a Test Area and each testcase is a t3 under it: `/release-test` runs only the t3s, so a Test Area needs at least one (see "Test numbers" under "Phase Selection").
Add new tests if needed based on the changes. Modify or remove existing ones if needed, as well.
Use for high level end-to-end test of an actual instance of Bees, used by an LLM
Use Plain English, do not list bees commands
Try to write tests that can be run in isolation
If you must write tests that depend on previous tests, ensure the ticket dependencies represent this. In `tests/integration.sh`, also mark each earlier test it depends on as a setup test (see "Setup tests" under "Phase Selection"), so a run that starts after it still runs it
Number a new test as "Test numbers" under "Phase Selection" says: a script-phase test bee gets no number in its title or body, a Claude-phase test case a `Test <N>:` title, numbered above its `up_dependencies`. Then update the `Tests in this phase:` ranges of the epics it shifts

### CI Phase Container

- **Test plan**: the phases run `b.qi9` from this checkout's `docker/testplans`, which `run_test.sh` mounts read-only into each phase container. `/ci` reads the same copy, from its files (see "CI Phase Status"). Neither looks the plan up among the host's registered hives: the hive registered as `testplans` there may be another checkout's copy or another repo's hive. If `docker/testplans/b.qi9/b.qi9.md` is missing, `run_test.sh` stops before the image build, a launch failure.
- **One phase per container**: each phase runs alone in its own fresh container, with bees already installed from test.pypi by `Dockerfile.test`. `run_test.sh <phase>` passes the phase number in as `PHASE`, and `docker/test_runner.sh` runs it with `tests/integration.sh` or a headless Claude run of `/release-test` (see "Bash Integration Test Script" and "Claude Phases").
- **Claude config and permissions**: no host Claude config file is mounted, since the host's can hold account details, API keys and host-only hooks. The phase container gets Claude auth only through the env vars `run_test.sh` passes (`CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`); its one mount is the test plan. `docker/entrypoint.sh` builds the container's `~/.claude.json` from those env vars, and installs the repo's `docker/claude-settings.json` (which `Dockerfile.test` copies into the image) as `~/.claude/settings.json`: permission rules only, no hooks. Nothing in the container can answer a prompt, so `test_runner.sh` runs Claude as the `testuser` user (not root), with stdin from `/dev/null` and `--dangerously-skip-permissions`. With that flag only the file's deny rules take effect: `AskUserQuestion` is denied. Its allow rules, which include every MCP server registered in the container (`bees`, `bees-stdio`, `bees-http`, `bees-prod`), apply only to a run without the flag.
- **Setup failures**: before the tests start, `test_runner.sh` sets up the phase (an API key, MCP server registrations, Phase 4's HTTP server, the testplans hive). An ERR trap, set once `PHASE` is checked, reports a setup command that fails: `TEST RUNNER EXITED: Phase N setup failed at docker/test_runner.sh line L, so no test ran: '<command>' exited with status S` (the command on one line, cut at 200 characters). The script then exits with that command's status, a crash for `/ci`.
  - Like `set -e`, the trap does not fire for a command tested by `if`, `while`, `until`, `!`, `&&` or `||`, nor on `exit`, so a setup step that prints its own crash line (the Phase 4 server check) gets no second one.
  - The script does not use `set -E`, so bash does not run the trap inside a shell function: setup must call none.
  - The trap is cleared just before the tests start: `tests/integration.sh` and the Claude run report their own ends.

### CI Bug Server

`/ci` runs each phase in its own Docker container (`docker/run_test.sh`). When a test fails, the container files a bug into this repo's bugs hive, through a bees HTTP server on the host. What the host needs for this (the bees install, a bugs hive, the port) is listed under [CI prerequisites](#ci-prerequisites).

- **Port**: `BEES_CI_PORT`, default 8473. This is CI's own port, separate from the `bees serve --http` default of 8000, which other services on a dev host often hold. `/ci` always starts the server with an explicit `--port`, so `http.port` in the global config cannot move it.
- **URL**: containers reach the server at `http://host.docker.internal:<port>`. Every container gets the same `--add-host host.docker.internal:host-gateway` mapping. If `BEES_MCP_URL` is set, `run_test.sh` uses that URL as-is. It must include an explicit port (e.g. `http://myhost:8473`): the in-container identity check rejects a URL without one.
- **Bind host**: the server must listen where `host.docker.internal` leads. On Linux Docker Engine, that is the default bridge gateway (e.g. `172.17.0.1`), and a server bound to `127.0.0.1` is unreachable from the containers. On Docker Desktop, that is the host's loopback. `docker/ci_bind_host.py` reads `docker network inspect bridge` output and prints the bridge gateway only if it is an address of this host, otherwise `127.0.0.1`. A successful bind is no proof, because some hosts allow binding non-local addresses, so the helper binds the gateway, listens, and connects to the bound socket with a 0.5 s timeout. That connection succeeds only for an address of this host. The helper never prints `0.0.0.0`, which would expose the server on every network. It prints only the address on stdout and the reason on stderr. `/ci` starts the server with `--host <bind host>`. `bees serve --http` defaults to `127.0.0.1`. Only the CI server uses the bind host.
- **Identity check**: `docker/check_bees_server.py` sends an MCP `initialize` request and accepts only a server whose `serverInfo.name` is `bees`. A `/health` check is not enough: another service on the same port may answer it too. `test_runner.sh` also runs it on Phase 4's own HTTP server before Claude starts (see "Claude Phases"). On the CI bug server, it runs at two points:
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
- **Filing a bug**: `docker/file_bug.py` files the bug in the container. It takes the hive from `--hive`, else `BEES_BUGS_HIVE`, else asks the server (`list_hives` for the repo root, then the `ci_bugs_hive.py` rule; `Dockerfile.test` copies that script next to `file_bug.py` for the import). It takes the repo root from `--repo-root`, else `BEES_REPO_ROOT`. There is no default path: without one it fails. No status is built in either: status names differ between hives, and bees refuses a status that is not among the hive's status values, and a missing one when it has values. So `file_bug.py` asks the server (`get_status_values` for the repo root) and resolves the hive's values as bees does: the hive's own list if it is not empty, else the scope's, else the global one. The bug gets the first value (`draft` in an Apiary Bugs hive), or no status when no level has values (freeform). A hive whose status is explicitly freeform shows in `get_status_values` like one without a list, so it gets the scope's or global first value, which its freeform status accepts. `get_status_values` keys the hives by normalized name, so `file_bug.py` normalizes the hive name first. It does not import bees, so it copies bees' `normalize_hive_name`, unchanged in behavior; `test_hive_name_normalization_agrees_with_bees` checks the copy against bees' own: change both together. The whole exchange with the server (connect, initialize, `list_hives`, `get_status_values`, `create_ticket`) gets 60 s (`FILE_BUG_TIMEOUT_SECONDS`), so a server that accepts the connection but never answers cannot hold the phase until `/ci`'s phase deadline. The limit also covers closing the MCP session. It prints `BUG FILED: <id>` on success. Every failure (no repo root, no bugs hive, status values refused, ticket rejected, server unreachable, not answering in JSON, or no answer within the limit) prints `BUG FILING FAILED: <reason>` and exits 1, so a failed filing still ends in a line `/ci` polls for.

`tests/test_check_bees_server.py` holds the unit tests for the identity check, the bind host choice, and the host-address proof (`local_address_error`). It also holds static checks of the CI scripts: the shared default port, the checks at the bind host, the in-container check between build and phase (a failed check stops `run_test.sh`), and the `/ci` skill stopping only a server a `/ci` run started, guarded by the command-line check, on every path that ends the run, and launching each phase as its own command. Further static checks cover portability and monitoring: no user home directory or Homebrew path in the CI scripts and skills, `run_test.sh` passing `BEES_BUGS_HIVE` and `BEES_REPO_ROOT` into the phase container and stopping before the build when no bugs hive is found, `run_test.sh` mounting this checkout's `docker/testplans` (which must hold `b.qi9`) and running `bees list-hives` only when `BEES_BUGS_HIVE` is not set, `run_test.sh` printing the `bees list-hives` output when that command fails, `run_test.sh` mounting no host Claude config (the test plan is its only mount), the container installing `docker/claude-settings.json` as its Claude settings (every MCP server registered in the container allowed, `AskUserQuestion` denied, no hooks), `test_runner.sh` starting Claude in Phase 4 only once the phase's own HTTP server passes the identity check (no `/health` probe; one check, between `bees serve` and the `bees-http` registration, of the URL `bees-http` is registered at; retried with a sleep, in a `for` loop of at most 120 tries; a `TEST RUNNER EXITED:` line and an exit before `bees-http` is registered when it fails), `Dockerfile.test` installing the `docker/` modules `file_bug.py` imports next to it, every `/ci` poll checking the phase deadline, and every signal `/ci` polls for being printed by a CI script. Tests that need a local stand-in for the bridge gateway use `127.0.0.2`. Tests of a host that allows non-local binding set `IP_FREEBIND` on the helper's sockets. Both run on Linux only.

`tests/test_ci_bug_filing.py` tests the bugs hive rule and `file_bug.py`. For the rule: `choose_bugs_hive` on the candidates within a scope and on which scope wins (own scope over inherited ones, ranking, ties, a queen repo's non-matching scopes), `test_scope_rule_agrees_with_bees` (matching and `compute_scope_specificity`, for exact paths, terminal `/*` and `/**`, wildcards anywhere and trailing slashes), and the `ci_bugs_hive.py` command line on real `bees list-hives` output across scopes and for a queen repo. For `file_bug.py`: the order in which it takes the hive and the repo root, the ticket it files, the status it gives the bug (`test_file_bug_gives_the_bug_the_hives_first_status`: an Apiary Bugs hive, the hive's list over the scope's and global ones, an empty hive list falling through to the scope's, global values only, an explicitly freeform hive taking the scope's value, no status when no level has values, and a `--hive` name that is not normalized), `test_hive_name_normalization_agrees_with_bees` (the copy of `normalize_hive_name` against bees' own, on names with capitals, hyphens, spaces, punctuation, a leading digit, non-ASCII letters, and empty), and the `BUG FILING FAILED:` line and exit 1 on each failure, including `get_status_values` refused (a repo root no scope matches), an unreachable server and a server that opens the session and then stops answering (given up at the time limit). It runs `file_bug.py` against the real bees MCP server in-process, with the hives in `tmp_path` (the `repo_with_hives` fixture, whose `status_values` argument sets the global, scope and per-hive status values), and the time limit test against a `stub_server`. No hive in its `file_bug.py` tests is named `bugs` (they use names like `team_bugs`, `triage` and `features`), so discovery passes only by the rule, never by a built-in name.

### CI Phase Monitoring

`/ci` reads each phase's result from its tmux pane. It uses the container state only to detect a crash (the container is no longer running).

- **Containers stay up**: in every phase, including the bash phases, the container's tmux session stays open after the test runner exits, with its last output on screen, until `/ci` removes the container. A running container says nothing about progress.
- **Signals**: the results are `RELEASE TEST PHASE N PASSED` and `BUG FILED:`. `/ci` checks them first, because a crash signal can print below a result. The crash signals are `BUG FILING FAILED:` (from `file_bug.py`, or from `fail_test` when `file_bug.py` printed neither line), `TEST RUNNER EXITED` and `--- Phase N exited` (printed by the host tmux session `run_test.sh` creates when it loses the container's session, for example because the container stopped). After a failed test, `tests/integration.sh` also prints `RELEASE TEST PHASE N FAILED` below the bug filing line. `/ci` does not poll for it: the bug filing line decides.
- **`TEST RUNNER EXITED`**: `docker/entrypoint.sh` prints `TEST RUNNER EXITED (status N)` whenever the test runner ends. When `test_runner.sh` itself ends a phase without a result, it first prints `TEST RUNNER EXITED: <reason>`, then exits non-zero. The reasons: a setup command that failed, after which it exits with that command's status (see "Setup failures" under "CI Phase Container"); and, with exit 1, Phase 4 setup whose HTTP server did not come up, a Claude run that ended without a result line, or a crash of `ci_claude_stream.py`, after which whether Claude printed one is not known (see "Claude Phases"). `/ci` matches both forms. A runner that stops with no result line ends in `TEST RUNNER EXITED`, a crash: for example, a bash phase in which no test ran (the start test number is past the phase's last test), an invalid `PHASE`, an error in `tests/integration.sh` outside any test, or one of the `test_runner.sh` reasons above. An error during a bash test, outside its checks, is not a crash but a failed test, with a bug filing line (see "Errors outside the checks" under "Phase Selection").
- **Last lines**: in a Claude phase, the result lines are repeated under `=== Result lines of this run ===` as the last lines of the pane, so they stay within the lines `/ci` captures however long the run's output.
- **Phase timeout**: `BEES_CI_PHASE_TIMEOUT_MINUTES`, default 60. `/ci` checks that it is a whole number greater than 0 before anything starts. Each phase's deadline is set when its launch returns. A phase with no signal by its deadline is handled as crashed, so a phase that never reports cannot hang `/ci`.
- **Crash report**: `/ci` names the cause: the bug could not be filed (with the reason from the `BUG FILING FAILED:` line), the phase timed out, or it crashed (with the reason from a `TEST RUNNER EXITED:` line, when there is one).

### CI Phase Status

With a status hive (below), `/ci` records each phase's result as the status of its epic under b.qi9: `pupa` (to run), `worker` (running), `finished` (passed), `failed` (bug filed or crashed), and `legendary` (set on every epic once all phases pass). A plain `/ci` skips `finished` and `legendary` epics, unless every epic has one of those statuses; then it starts a fresh run. `/ci full` runs every phase. `/ci <test number>` starts at that test's phase: the phases before it do not run, and with a status hive they are marked `finished`.

- **Reading the plan**: `/ci` runs `bees list-hives | python3 docker/ci_plan.py` from the checkout root. `docker/ci_plan.py` reads `b.qi9` from this checkout's `docker/testplans` files, the copy the containers run, and prints JSON: the phases in the plan's `children` order (1st child is Phase 1), each with its epic's ID, title and status, then `status_hive` and `status_hive_reason`. It exits 1 only when it cannot read the plan; `/ci` then stops. The skill never reads or writes the plan through the bees MCP tools: the host's `testplans` hive may be another copy (in a worktree, usually the main checkout's). It finds a test number's phase in the same files: the epic whose directory holds a test titled `Test <N>:`, else the epic whose body gives a `Tests in this phase:` range that holds the number. Titles and ranges match the tests each phase runs (see "Test numbers" under "Phase Selection").
- **Phase order**: `/ci` runs every phase `ci_plan.py` lists that is in the run scope, however many the plan has. Phase 1, the plan's first child, is the gatekeeper: when it is in the run scope, it runs alone, and the other phases start only if it passes. Then every other phase in the run scope launches in parallel, each with its own container, tmux session `bees-ci-<N>` and deadline.
- **Status hive**: the hive `/ci` writes statuses through, matched by path, never by name. Of the hives `bees list-hives` lists, `ci_plan.py` takes those in scopes matching the repo root and, for each name, the most specific scope's definition, as bees resolves a name there. The status hive is the one whose path, symlinks resolved, is this checkout's `docker/testplans`. A name that two equally specific scopes give different paths does not count, since which one bees uses is not certain, and neither does a hive with a relative path. If `bees list-hives` fails, there is no status hive, and the reason relays bees' error. Scope matching and ranking come from `ci_bugs_hive.py`.
- **With a status hive**: each status change is `bees update-ticket --ids <epic IDs> --status <status> --hive <status_hive>`, run from the checkout root. A failed write is reported and the run continues: a status is a record, not a test result.
- **Without one**: `/ci` records nothing. It runs every phase, as with `full`, since no run could update the statuses it would skip by, and tells the user once: "Phase statuses will not be recorded: <reason>. Running all phases." A test number still skips the phases before its phase.
- **Limitation**: in a worktree whose `docker/testplans` is not registered as a hive bees resolves there, `/ci` cannot resume: no statuses are recorded, so every run starts again at Phase 1, or at the given test's phase.
- **Stdlib only**: `ci_plan.py` runs on the host with plain `python3`, so it reads ticket frontmatter itself, not with PyYAML. It reads only what the plan's fields need, as bees writes them: plain, quoted and null scalars, block lists, and values wrapped onto a second line.

The testplans hive rejects any status not listed in `status_values` in `docker/testplans/.hive/identity.json`, so the skill and that file must agree. If you add a status to the skill, add it there too.

`tests/test_ci_skill.py` tests `ci_plan.py`: the phases in `children` order, plans it cannot read, frontmatter read as PyYAML reads it (bees' own writer output included), and its command line, with and without a hive list. The status hive tests cover this copy under any name or through a symlink, another copy only, the most specific scope winning or shadowing, equally specific scopes, a queen repo's non-matching scopes, a glob scope and a relative path; for each hive picked, they check that bees resolves that name for the repo root to this copy. Static checks on the skill: it pipes `bees list-hives` into `ci_plan.py`, it never names `show_ticket`, `update_ticket` or `bees show-ticket`, every `update-ticket` command has `--status` and `--hive`, every status the skill sets or reads is allowed, and its commands name no phase number but Phase 1, the gatekeeper (every later phase is launched and polled through a `<N>` placeholder; any number in a `run_test.sh` phase argument or a `bees-ci-` session name counts as a fixed phase). A static check on the release-test skill: it gives no list or range of phase numbers (such as `1, 2, 3, or 4`, `3/4`, `1-4`, `2 through 6` or `Phase 3 and Phase 4`).

## Bash Integration Test Script

In CI, `docker/test_runner.sh` runs Phases 1, 2, 5 and 6 of the integration test suite with a standalone bash script (`tests/integration.sh`). These phases exercise the installation and the CLI end-to-end — hive management, ticket CRUD, queries, dependencies, reference materials and resolvers, and more — without requiring an API token or LLM session. They are fast, deterministic, and safe to run on every change.

For Phases 3 and 4, and any other phase number (for example a phase added to the plan later), it runs Claude headless with the `/release-test` skill (see "Claude Phases"). Phases 3 and 4 validate the full LLM-agent interaction loop against a live MCP server (stdio and HTTP), catching interaction-level bugs that bash cannot. The split keeps the CLI phases fast while reserving token spend for the tests that genuinely need it.

### Phase Selection

- **`PHASE` is required**: `docker/test_runner.sh` has no default phase. It stops with exit 1 unless `PHASE` is a positive integer, then exports it, since both runners read it from the environment. `tests/integration.sh` runs only the phase in `PHASE`. A missing, empty or non-numeric `PHASE`, or one the script does not run, prints an error to stderr and exits 2 before any test runs. The script never runs every phase.
- **Bash phases**: `SCRIPT_PHASES` in `tests/integration.sh` lists the phases it runs. The phase condition that sends phases to the script in `docker/test_runner.sh` must list the same phases. To move a phase between bash and Claude, change both.
- **Sections**: every test section starts with a `# === PHASE N: <NAME> ===` header, followed on the next line by `phase_section N`. Each test after it belongs to Phase N, whether the section runs it with `run_test` or, for a setup test, `run_setup_test` or `run_phase_setup_test` (see "Setup tests"). Only setup and the end of the script (configuration, helper functions, phase selection, success signal) have untagged headers, and they hold no tests. A new section goes among the sections of its own phase (see "Test numbers"). It needs both lines, its setup tests marked, its name added to that phase in `tests/test_integration_phases.py`, its area added to the area list in that phase's `b.qi9` epic, and the `Tests in this phase:` ranges of the script phases it shifts updated.
- **Sections per phase**:
  - Phase 1: installation
  - Phase 2: hive management, tier configuration, ticket CRUD, dependencies, ID/GUID validation, status behavior, freeform queries, named queries, body file / chunk file
  - Phase 5: index generation, undertaker, move bee, sanitizer, error handling, test config mode, setup, sting, status values, glob-scope status values, uninstall, clone, fast parser pipeline, colonize --scope, scope-aware hive registration, cross-scope inheritance, ID charset and hierarchical IDs, single tests, hive portability (`identity.json`)
  - Phase 6: reference materials, update-config, resolver registry
- **Test numbers**: global. `run_test` (which the setup variants call) numbers every test in script order, whether or not its phase runs, so a test has the same number in every phase's run. The optional start-test-number argument (`START_TEST` in CI) skips the tests numbered below it, except the setup tests the tests from it on need, which run first (see "Setup tests"). One number belongs to one phase, the one whose epic's `Tests in this phase: <first>-<last>` range holds it, so `/ci <N>` starts the phase that runs test N (see "CI Phase Status"):
  - **Script phases**: the sections are grouped by phase, in `SCRIPT_PHASES` order, so each script phase's numbers are contiguous and are exactly its epic's range. The ranges are the only test numbers in their plan data: no test bee of a script phase has a `Test <N>:` title, and no epic or test body names a test number (a body that points at tests names their `tests/integration.sh` section instead). Adding, removing or moving a script test shifts the numbers after it, so it means updating only the ranges of the script phases it shifts.
  - **Claude phases**: their tests are numbered only by their `Test <N>:` titles, from 301 up, so a script test can be added without renumbering a Claude test. The script's numbers must stay below 301. `/release-test` runs the phase's test cases, the t3s of its Test Areas (the epic's t2s), in `up_dependencies` order. So:
    - Every Test Area has at least one test case. A Test Area without one runs nothing, whatever its own body describes.
    - Every test case has a `Test <N>:` title, and the phase's titles fill its range exactly, so `/ci <N>` and `/release-test <N>` can start at any test the phase runs.
    - A test case is numbered above each of its `up_dependencies` (tests of its own Test Area). `/release-test <N>` runs N's `up_dependencies` first and skips the other tests before N, so "before N" is "numbered below N".
    - Adding or removing a Claude test renumbers the Claude titles after it and the ranges they shift.
- **Setup tests**: a test may need state that earlier tests of its section set up (a hive, a ticket, a registered resolver, installed hooks), or set up and then undo (`test_hm_rename_back` restores the name `test_hm_rename` changed). Each such earlier test is a setup test: its section runs it with `run_setup_test`, not `run_test`. Rule: a test may rely only on the state of the setup tests before it, in its own section or held for its phase (below), never on a test run with `run_test`, which a start number after it skips.
  - A setup test of the current phase numbered below the start test number is held, not skipped. Right before the first test that runs, the held setup tests run, in test order, under their own numbers, each after a `[SETUP] Test N (<fn>) ...` line naming the start test.
  - A new section drops the setup tests still held from the section before it: none of that section's tests ran, so none needs them. `run_phase_setup_test` holds a setup test to the end of its phase instead, for state a later section of the phase uses too: `test_crud_setup` (its hive also holds the BODY FILE / CHUNK FILE tickets) and `test_error_setup` (Error Hive, which ID CHARSET AND HIERARCHICAL IDS and `test_t9_cap` use, and the config file and `/test-repo` scope later Phase 5 sections need).
  - So a held setup test runs only right before a test numbered at or above the start number, never alone: a start number past the phase's last test still runs no test. A setup test that runs counts like any other test, and its failure fails the phase.
  - `run_numbered_test` runs and counts every test that runs, setup tests included; `run_test` only decides which tests run and holds the setup tests.
  - A test named `test_*_setup` must run as a setup test.
- **Results**: when the phase passes, the script prints `RELEASE TEST PHASE N PASSED` with the phase it ran, then `Tests passed: <passed> / <ran>`, both counted in tests: a test that passes several checks counts once, and the held setup tests that ran first count too. On the first failure, `fail_test` prints the `[FAIL]` line, the bug filing output (`BUG FILED:` or `BUG FILING FAILED:`), then `RELEASE TEST PHASE N FAILED`, and exits 1. If `file_bug.py` printed neither filing line (it crashed first, for example on an import), `fail_test` adds `BUG FILING FAILED: file_bug.py exited with status S without filing the bug (its output is above)`, so every failure ends in a line `/ci` acts on. If no test of the phase ran (for example, the start test number is past the phase's last test), the script prints an error to stderr and exits 1, with no pass line.
- **Errors outside the checks**: the script runs under `set -euo pipefail`, so a command that fails outside the assert helpers (for example a `kill` of a server process that already died) ends it. An ERR trap, inherited by the tests through `set -E`, reports that as the failure of the running test, through `fail_test`: `[FAIL] Test N: <fn> stopped at tests/integration.sh line L, outside its checks: '<command>' exited with status S` (the command on one line, cut at 200 characters), then the bug filing line and `RELEASE TEST PHASE N FAILED`. `run_numbered_test`, which runs every test (held setup tests included), records the running test's function name in `CURRENT_TEST`, and clears it after the test.
  - An error that ends the script without a failing command (an unset variable under `set -u`, a bad substitution) fires no ERR trap. The EXIT trap reports it during a test as `[FAIL] Test N: <fn> stopped with status S outside its checks (the error is printed above)`. An exit status of 128 or more is a signal from outside (for example the session closing), not a test failure.
  - Between tests, no test failed: the ERR trap prints `ERROR: tests/integration.sh line L, outside any test: '<command>' exited with status S`, files no bug, and the phase ends in `TEST RUNNER EXITED`, a crash.
  - Only one failure is reported per run, and a failure while reporting only ends the script. Only the main shell reports: a failure inside a subshell or command substitution reaches it as the failure of the command that ran it.
  - Like `set -e`, the trap does not fire for a command tested by `if`, `while`, `until`, `!`, `&&` or `||`: a test step that may fail without failing the test must be written that way.
  - The script has one EXIT trap. A test that needs its own exit handling must merge it into that trap, not set another, which would replace it.

`tests/test_integration_phases.py` never runs `tests/integration.sh`. Most of its checks are static, text-only (plus `bash -n`): that the routing, `SCRIPT_PHASES`, section tags, sections per phase, result lines (`Tests passed` counting tests, not checks), the ERR and EXIT traps and the `fail_test` filing fallback stay as described above. For those traps: one of each, set, with `set -E`, before the first test; each reports through `fail_test` only during a test and only once, with the ERR trap off while reporting; the ERR trap reports from the main shell only, with the line and the command. It also checks `test_runner.sh`'s setup ERR trap (see "Setup failures" under "CI Phase Container"): one, set before the first setup command, printing a `TEST RUNNER EXITED:` line that names the command and exiting with its status, and cleared before `tests/integration.sh` or Claude starts. Every trap handler takes the failing status first, before any other command resets `$?`. For the test numbers, it reads the plan from this checkout's `docker/testplans` files, as `/ci` does: each script phase's numbers are exactly its epic's range, and all are below every Claude phase's range; each Claude phase's `Test <N>:` titles fill its range; no number titles two tests, and no ticket of a script phase has a `Test <N>:` title; in each Claude phase, taken as `/release-test` collects it (the epic's `children`, then each Test Area's), every Test Area has a test case, every test case has a `Test <N>:` title and their numbers are exactly the phase's range, and every test case is numbered above each of its `up_dependencies`; and for every test number, the `/ci` lookup (title, then range) gives the phase that runs it, so a `Test <N>:` title outside every epic's directory fails this check. It also reads every ticket in `docker/testplans` with bees's reader and runs the linter's guid check on it without auto-fix, so no plan file is written: each guid must be `GUID_LENGTH` long, all in `ID_CHARSET`, and start with its ticket's short ID. Sanitize cannot fix a wrong guid, so a hand-written plan ticket needs a guid that passes.

The setup test checks run a replay with bash instead: a script built from `tests/integration.sh`'s configuration assignments, helper functions, `phase_section` and test calls in order, and success signal, with each test a stub that only passes (no bees command, environment guard or trap). For every test number as the start number of its phase, the replay must run the held setup tests of its section and those held for its phase, in test order under their own numbers, then every test of the phase from it on, and no other test. Starts inside REFERENCE MATERIALS and RESOLVER REGISTRY, starts in sections that need a phase-held setup test, and a start in UPDATE CONFIG, which needs none of REFERENCE MATERIALS' setup tests, are also checked by name, with `Tests passed` counting the setup tests that ran. For every script phase, a start number past its last test must run no test, not even a held setup test, and the phase must fail with exit 1 and no pass line. A static check fails any `test_*_setup` run with plain `run_test`.

### Where It Runs

`tests/integration.sh` runs only inside a CI phase container, where `docker/test_runner.sh` starts it with `PHASE` and the optional start test number. The container gives it what it needs: bees installed from test.pypi with the `serve` extra, the `/test-repo` directory it works in, and a throwaway home whose `~/.bees/config.json` it overwrites.

**Never run `tests/integration.sh` on a host.** It stops at once where there is no `/test-repo` directory, as on a host, and wherever it does run, it overwrites `~/.bees/config.json`, the global config that registers every hive on the machine. Run the suite in Docker (below).

### Claude Phases

- **Headless run**: `docker/test_runner.sh` runs Claude non-interactively (`claude -p`), with the prompt `/release-test`, or `/release-test <START_TEST>` when a start test is given, and stream-json output. The run exits when it is over, so a run that gives up ends its phase at once. Permissions are skipped (see "CI Phase Container").
- **The pane**: the run's output is piped through `docker/ci_claude_stream.py` (stdlib only, copied into the image), which prints it to the tmux pane `/ci` reads as it happens: a `--- Claude started: model M, MCP servers: <name> (<status>), ... ---` line, Claude's text, each tool call (its first 200 characters), the first 8 lines of each tool result, API retries, permission denials, and any output line that is not a stream-json event, as it is. When the run's final result event arrives, it prints the error text of a run that failed, then `--- Claude run ended: <outcome> ---`; a stream that ends without that event gets no such line. It never prints a prompt, such as the skill text, which quotes the result lines. If the pane goes away, it reads on to the end of the stream, so Claude keeps its output pipe, and exits as it would have with the pane.
- **Result lines**: `RELEASE TEST PHASE N PASSED` for this phase, `BUG FILED:` and `BUG FILING FAILED:`. They count in Claude's text anywhere in a line, and in a tool result only at the start of a line, where `file_bug.py` prints them: a tool result that merely quotes one (a file Claude read, say) does not count. When the stream ends, the script prints the result lines it saw again, under `=== Result lines of this run ===`, as the last lines of the pane, and exits 0.
- **No result line**: the script exits 1 and writes the outcome, one line on how the run ended, to a file. `test_runner.sh` then prints `TEST RUNNER EXITED: Claude ended without printing a result line (claude exit status S): <outcome>` and exits 1, a crash for `/ci`. The outcome says whether the run finished or failed (with its subtype) and, when known, its turns, duration, number of denied tool calls and Claude's last message (its first 200 characters). For a stream that ends with no final result, it says the run stopped early, with its last output above. If the outcome file is missing or empty, the outcome is `ci_claude_stream.py exited with status 1 before it could say how the run ended`.
- **Formatter crash**: any exit status of `ci_claude_stream.py` other than 0 or 1 is a crash of the script, which says nothing about Claude's run. `test_runner.sh` then prints `TEST RUNNER EXITED: ci_claude_stream.py crashed (status S), so whether Claude printed a result line is not known (claude exit status C). Its error and the run so far are above.` and exits 1, a crash for `/ci`. `test_runner.sh` reads both exit statuses, Claude's and the script's, with `set -e` off, right after the pipeline.
- **Phase 3 setup**: registers `bees-stdio`, a stdio MCP server.
- **Phase 4 setup**: starts `bees serve --http` on port 9000 in the background, then checks it with `docker/check_bees_server.py` (MCP `initialize`, `serverInfo.name` must be `bees`) before it registers `bees-http` and starts Claude: without the server, Claude finds no `bees-http` tools and gives up. The check is retried once a second, up to 30 tries (`HTTP_SERVER_WAIT`), while nothing listens (check exit 1) and the server process runs. It stops early when the connection is not refused but no bees MCP server answers (check exit 2: another service, a reset, a timeout or a TLS failure) or the check fails otherwise (exit 3, a usage error), or when the server process has exited. On failure, `test_runner.sh` prints the last 20 lines of the server's log (`/tmp/bees_http.log`) and of `~/.bees/mcp.log`, then `TEST RUNNER EXITED: Phase 4 setup failed, so Claude was not started: the bees HTTP server did not come up at http://127.0.0.1:9000: <reason>. Its logs are above.`, and exits 1. The reason is the check's output when the check stopped early, `the bees serve process exited with status N`, or, after the last try, `no answer within 30 s (<check output>)`.

`tests/test_ci_claude_stream.py` tests `ci_claude_stream.py` on stream-json events made up in the test: the result lines it finds and where, its exit code, the result lines repeated last, what the pane shows, the outcome line of a run that finished, failed or stopped with no final result, events it cannot read, and usage errors. It also runs the script from the command line, as `test_runner.sh` does, with bytes that are not UTF-8 on stdin: exit 0 with a result line, 1 without, also when nothing reads its output any more (the pane gone), and an outcome file written either way. Its static checks read `test_runner.sh` as text, never run it: Claude runs headless (`-p`, stream-json, stdin from `/dev/null`, permissions skipped) through the script, from where the image installs it; both exit statuses are read with `set -e` off, right after the pipeline; and the script's status picks the branch: 0 returns, any status but 1 prints the formatter crash line, 1 the line for a run without a result line. The Phase 4 server check is tested in `tests/test_check_bees_server.py`, and the setup trap cleared before Claude starts in `tests/test_integration_phases.py`.

## Running the Integration Suite

The integration suite runs only in Docker: through `/ci`, a Claude Code skill, or for one phase, `docker/run_test.sh <phase>` (below); never through `tests/integration.sh` on a host. Run `/ci` from this checkout's root. It publishes the current code to test.pypi (`docker/publish_test_pypi.sh`), starts each phase in its own container with `docker/run_test.sh <phase> [start-test-number]`, and reads each phase's result (see "CI Phase Monitoring"). Set up a new machine first: see [CI prerequisites](#ci-prerequisites).

- **The suite**: `/ci`. With a status hive, it skips the phases that passed in the last run; `/ci full` runs every phase (see "CI Phase Status").
- **From a test number**: `/ci <test-number>` finds the test's phase in the plan and leaves out the phases before it. It passes the number to that phase's `run_test.sh` as the second argument, which reaches the container as `START_TEST`: that phase skips its tests numbered below it, except those that run first for the state later tests need (in a bash phase, the held setup tests, see "Setup tests" under "Phase Selection"; in a Claude phase, the start test's `up_dependencies` chain, as the `/release-test` skill says), and every later phase in the run scope runs all its tests.
- **One phase**: `/ci` has no option for this. Run `docker/run_test.sh` yourself, from the checkout root, once the setup `/ci` does in its first two steps is in place:

```bash
BEES_VERSION=<version> ./docker/run_test.sh <phase> [start-test-number]
```

`BEES_VERSION` must be a version already on test.pypi: `docker/publish_test_pypi.sh` publishes the current code and prints its version on its last line. A bees HTTP server must be running on `BEES_CI_PORT` at the bind host (see "CI Bug Server"); if none is, `run_test.sh` stops and prints the `bees serve` command that starts one. `run_test.sh` returns once the container is up: attach with `tmux attach -t bees-ci-<phase>`. When the phase is done, remove its container and session (`docker rm -f bees-ci-<phase>`, `tmux kill-session -t bees-ci-<phase>`), and stop any bees server you started for it, since that server has no authentication. A phase run this way records no phase status.

## CI prerequisites

What a machine needs before its first `/ci` run. All of it is on the host, where `/ci` and the scripts it runs (`docker/publish_test_pypi.sh`, `docker/run_test.sh`) use it. Set the env vars named here in the environment Claude Code runs in: `/ci` runs the scripts from there.

### Tools

| Tool | Used for |
|------|----------|
| Claude Code (`claude`) | Runs the `/ci` skill. `claude setup-token` makes the token for the CI containers (below) |
| Docker | `run_test.sh` builds the `bees-test` image and runs each phase in its own container. The daemon must be running and your user able to use it (`docker info` succeeds). If your user is in the `docker` group but the login session predates that, `run_test.sh` and `/ci` fall back to `sg docker` |
| tmux | `run_test.sh` opens a host session `bees-ci-<N>` attached to each phase container's session, and `/ci` reads each phase's result from it |
| rsync | `run_test.sh` copies the checkout into a temporary Docker build context, with symlinks dereferenced |
| curl | `publish_test_pypi.sh` polls the TestPyPI index until the new version shows up |
| python3 | The stdlib-only helpers in `docker/` that run on the host: `check_bees_server.py`, `ci_bind_host.py`, `ci_bugs_hive.py` and `ci_plan.py` |
| poetry | `publish_test_pypi.sh` builds the package (`poetry build`) |
| twine | `publish_test_pypi.sh` uploads the build to TestPyPI. It is not a dependency of this project: install it on your `PATH`, for example with `pipx install twine` |
| bees, with the `serve` extra | The host's own bees. `/ci` starts `bees serve --http` on the CI port, the server the containers file bugs through; `run_test.sh` and `/ci` run `bees list-hives`; `/ci` records phase statuses with `bees update-ticket`. Install it with `pipx install 'bees-md[serve]'`, or from this checkout with `poetry install -E serve` and that environment's `bees` on your `PATH` |

**Network**: outbound access to test.pypi.org and pypi.org; Docker Hub, where the image build pulls `ubuntu:22.04`; the Ubuntu, Node.js and npm package sources the image build installs from; and the Anthropic API, which the Claude-run phases call from inside the containers.

### Claude auth for the CI containers

`run_test.sh` passes one Claude credential into each phase container, and stops before the image build if it finds no credential. Every phase needs one, though only the Claude-run phases use it. `run_test.sh` checks these sources in this order, and uses the first credential it finds:

1. `~/.secrets/claude_oauth_token`: an OAuth token (whitespace removed)
2. `CLAUDE_CODE_OAUTH_TOKEN`
3. `~/.secrets/anthropic_api_key`: an Anthropic API key
4. `ANTHROPIC_API_KEY`

So an OAuth token, from either place, wins over an API key, and a file wins over its env var: a stale token file hides a newer `CLAUDE_CODE_OAUTH_TOKEN`. A file that is missing, unreadable or empty is skipped. The container gets an OAuth token as `CLAUDE_CODE_OAUTH_TOKEN`, an API key as `ANTHROPIC_API_KEY` (see "CI Phase Container"), where anyone with Docker access on the host can read it. Prefer the files, since the host's Claude Code also logs in with these env vars.

- **OAuth token** (tried first): needs a Claude Pro, Max, Team or Enterprise plan. Run `claude setup-token` and sign in in the browser when it asks. It prints a token valid for one year (`sk-ant-oat01-…`) and saves it nowhere. Create a private file for it, then paste the token into the file with an editor or `cat >`. Don't put the token on a command line, which leaves it in your shell history.

  ```bash
  mkdir -p -m 700 ~/.secrets
  touch ~/.secrets/claude_oauth_token
  chmod 600 ~/.secrets/claude_oauth_token
  ```

- **API key** (used only when no OAuth token is found): an Anthropic API key, billed per use, created under API keys in the Claude Console (platform.claude.com). Store it the same way in `~/.secrets/anthropic_api_key`, or set `ANTHROPIC_API_KEY`.

### TestPyPI token

`/ci` first publishes the current code to TestPyPI with `publish_test_pypi.sh`, and the phase images install it from there. Only twine, on the host, uses the token.

1. Get the Owner or Maintainer role on the `bees-md` project on test.pypi.org, which uploading needs: ask a project owner to add your account. TestPyPI accounts are separate from pypi.org accounts.
2. On test.pypi.org, under Account settings → API tokens, add a token scoped to the `bees-md` project. Copy it (`pypi-…`): it is shown only once.
3. Put it in `~/.pypirc` with an editor, in a `[testpypi]` section, then make the file private with `chmod 600 ~/.pypirc`:

   ```ini
   [testpypi]
   username = __token__
   password = pypi-<your TestPyPI token>
   ```

`publish_test_pypi.sh` needs a `[testpypi]` section in `~/.pypirc`, and stops before building without one. It uploads with `twine upload --repository testpypi --non-interactive`, so twine reads the username and password from that section and never prompts. Twine knows the TestPyPI upload URL, so a `repository =` line is optional. If the file has a `[distutils]` section, its `index-servers` must list `testpypi`, or twine ignores the `[testpypi]` section.

### Hives and port

- **Bugs hive**: the host's bees must list a bugs hive for this checkout (see "Bugs hive rule" under "CI Bug Server"), or `BEES_BUGS_HIVE` must name one; otherwise `run_test.sh` stops before the image build. To create one, run `bees colonize-hive --name bugs --path <absolute path>` from the checkout root.
- **Status hive** (optional): for `/ci` to record phase statuses and resume a run, register this checkout's `docker/testplans` as a hive (see "CI Phase Status"), for example with `bees colonize-hive --path <absolute path of docker/testplans>` from the checkout root, which takes the name from the hive's marker.
- **`BEES_CI_PORT`** (default 8473): the host port of the bees server the containers file bugs through. Set it to a free port if another service holds 8473. A host firewall must let the containers reach the host on that port.

## Checklist for New Tests

1. Can I parametrize instead of writing N separate tests?
2. Can I use a shared fixture instead of copy-paste setup?
3. Am I testing behavior or implementation?
4. Does this constant wrap a simple string? (inline it)
5. Is this a meta-test? (delete it, unless it is a real-home isolation guard test in `tests/test_conftest.py`)
6. Did I read the target file's docstring?
7. Is a similar test already written?
8. Have you added some tests to the Integration test bee?
