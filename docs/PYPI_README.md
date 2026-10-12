## Overview

Bees is a markdown-based ticket management system for LLM-assisted development. After install the `bees` command is available in your shell.

## Installation

```bash
# CLI only
pipx install bees-md

# CLI + MCP server (required for bees serve)
pipx install 'bees-md[serve]'
```

Check the installed version:

```bash
bees --version
```

## Upgrade

Reinstall instead of upgrading in place. An in-place upgrade (`pipx upgrade`, `pipx install --force`, `pip install -U`) can leave the MCP server's `fastmcp` package half-installed, and `bees serve` then cannot start.

```bash
pipx uninstall bees-md
pipx install 'bees-md[serve]'
```

With pip instead of pipx:

```bash
python -m pip uninstall -y bees-md fastmcp fastmcp-slim mcp
python -m pip install 'bees-md[serve]'
```

## Documentation

Full docs at [github.com/gabemahoney/bees](https://github.com/gabemahoney/bees)

## Changelog

See [Releases](https://github.com/gabemahoney/bees/releases) for version history and release notes.
