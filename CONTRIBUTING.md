# Contributing

## Development Setup

```bash
# Clone and install with MCP server support (needed for dev)
poetry install -E serve
```

The `serve` extra installs `fastmcp` and its dependencies, required for running the MCP server (`bees serve`). Without it, only the CLI is available.

### Install paths

| Command | What you get |
|---------|-------------|
| `poetry install` | CLI only (pyyaml) |
| `poetry install -E serve` | CLI + MCP server (fastmcp) |
| `pip install bees-md` | CLI only |
| `pip install 'bees-md[serve]'` | CLI + MCP server |

### Running

```bash
poetry run bees --help          # CLI
poetry run bees serve --http    # MCP server (requires -E serve)
```

## CLI/MCP Parity

Any capability added via CLI flags must have a corresponding MCP tool parameter, and vice versa. When adding a new CLI flag that accepts a file path (e.g. `--body-file`), add the equivalent `_file` parameter to the corresponding MCP tool (e.g. `body_file`). The one permitted asymmetry is stdin (`"-"`): CLI file flags may accept `-` as a path to read from stdin; MCP tool file parameters must not (stdin is not available in the MCP context — raise `ValueError` when the path is `"-"`).

File-sourced content is stored as written, on both surfaces. Inline body text has literal `\n` / `\t` expanded into a newline / tab (to undo LLM JSON double-escaping), but file content must not be: a new body or chunk file flag or parameter must pass `unescape_body=False` / `unescape_chunk=False` to the core function.

## Testing and Publishing

Package name: `bees-md`
PyPI: https://pypi.org/project/bees-md/

### Run the test suite

Use the `/ci` skill from Claude Code. It publishes the current code to test.pypi, builds a Docker image, and runs the full release test suite in parallel phases.

```
/ci
```

The integration tests run only in Docker: through `/ci`, or for one phase, `docker/run_test.sh <phase>` (see [Running the Integration Suite](docs/architecture/testing.md#running-the-integration-suite)). Never run `tests/integration.sh` on your machine: it runs only inside a CI container, and it overwrites `~/.bees/config.json`. To start from a test number, run `/ci <test-number>`.

Before the first run on a machine, set up the [CI prerequisites](docs/architecture/testing.md#ci-prerequisites): Claude auth for the CI containers, a TestPyPI token, the tools CI runs, and a bugs hive.

Test failures are filed as bugs against a bees HTTP server on the host, on port 8473 by default. `/ci` starts that server if nothing is listening there. It binds the address the containers reach the host at: the Docker bridge gateway on Linux Docker Engine, `127.0.0.1` on Docker Desktop. The server has no authentication, so when the run ends, `/ci` stops a server that `/ci` started, including one an interrupted earlier run left running. A server you started yourself keeps running. If another service already uses port 8473, set `BEES_CI_PORT` to a free port in the environment Claude Code runs in. If a host firewall blocks traffic from containers to the host on that port, `/ci` stops before the tests start and says so.

The containers run the test plan `b.qi9` from this checkout's `docker/testplans`. `/ci` records each phase's result there, as its epic's status, so a later `/ci` runs only the phases that did not pass; `/ci full` runs them all. It records them only through a hive, under any name, that bees resolves for this checkout to its `docker/testplans`. Without one, for example in a worktree whose `docker/testplans` is not registered, `/ci` records nothing and runs every phase each time, so it cannot resume a run. It says so when it starts.

Bugs go into this repo's bugs hive: the hive named `bugs`, else the only hive whose name contains `bugs`. A bugs hive in this repo's own scope wins over one in a broader scope it inherits from. If no hive fits, or several do, set `BEES_BUGS_HIVE` to the hive's name. Hives are looked up for this checkout; set `BEES_REPO_ROOT` to look them up for another path. Each bug gets the first status value configured for the bugs hive, its scope or globally, or no status if none is set. A phase with no result after 60 minutes is reported as timed out; set `BEES_CI_PHASE_TIMEOUT_MINUTES` to change the limit.

### Publish to PyPI

Use the `/publish` skill from Claude Code. It bumps the version, builds, checks, uploads to PyPI, commits, and tags the release.

```
/publish
```
