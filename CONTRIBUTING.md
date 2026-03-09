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

## Testing and Publishing

Package name: `bees-md`
PyPI: https://pypi.org/project/bees-md/

### Run the test suite

Use the `/ci` skill from Claude Code. It publishes the current code to test.pypi, builds a Docker image, and runs the full release test suite in parallel phases.

```
/ci
```

### Publish to PyPI

Use the `/publish` skill from Claude Code. It bumps the version, builds, checks, uploads to PyPI, commits, and tags the release.

```
/publish
```
