# Bees 🐝

[![PyPI version](https://img.shields.io/pypi/v/bees-md?color=yellow)](https://pypi.org/project/bees-md/)
[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-yellow.svg)](https://www.python.org/)

Bees is a ticket system for LLMs that stores tickets on disk as markdown. It's designed to be configurable for custom workflows.


## Usage

Use natural language to instruct your LLM to use Bees.
Follow the installation instructions then ask your LLM to create a `hive` which is where your tickets will live.
You are now ready to start using bees. See the [Advanced Usage](#advanced-usage) section for more advanced features.

## Features
🐝 **Hives allow custom workflows**
- Hives organize tickets into folders and allow custom status and hierarchy levels
- Each hive can have its own status types (e.g, a Bugs hive with `open`, `closed` and `verified`)
- Define levels and names of child hierarchies per hive (e.g, a Features hive with `Epics`, `Tasks` and `Subtasks`)

🐝 **Tickets are plain markdown files on disk**
- Human-readable and editable
- No database required
- Human-navigable `index.md` per hive (with optional Mermaid dependency graphs)

🐝 **Simple but powerful YAML query pipeline designed for your agent**
- Traverse parent/child and peer dependency relationships
- Filter by status, ticket type, tags, title, hive, parent, and ID
- Save named queries for reuse across sessions

🐝 **Attach references to tickets in any format** 
- Store paths to source documents you want to make available to LLMs reading the ticket
- Support for optional custom resolvers to pre-transform egg values to resources for calling LLMs 

🐝 **Archives tickets based on a query you define**
- Archived tickets move to a `/cemetery` directory, excluded from all queries and operations
- Run manually or schedule automatic archival in HTTP server mode

🐝 **Every operation is available via CLI and MCP server (stdio or HTTP)**
- HTTP mode adds an in-memory stat cache for read performance at scale

## Minimal Installation

```bash
# CLI only
pipx install bees-md

# CLI + MCP server (required for bees serve)
pipx install 'bees-md[serve]'
```

### CLI Context Injection

The following script installs `bees sting` hooks into Claude Code's settings (`SessionStart` and `PreCompact`).
On each session start, Claude Code will automatically receive the bees CLI reference so your LLM knows how to use bees without you documenting it in memory files.
You can skip this and just tell your LLMs to use `bees -h` to learn how to use it.

```bash
bees setup claude cli
```

### MCP Server

You can run bees as a stdio or HTTP MCP server. 
HTTP mode adds an in-memory stat cache for read performance at scale and supports an `undertaker` schedule that automatically archives tickets based on a query you define.

<details>
<summary>Claude Code + MCP</summary>

```bash
# stdio (user scope)
claude mcp add --transport stdio --scope user bees -- bees serve --stdio

# stdio (project scope, writes to .mcp.json)
claude mcp add --transport stdio --scope project bees -- bees serve --stdio

# HTTP
claude mcp add --transport http --scope user bees http://127.0.0.1:8000/mcp
bees serve --http > /tmp/bees_server.log 2>&1 &
```

Verify:

```bash
claude mcp list
```

</details>

<details>
<summary>OpenCode + MCP</summary>

Add to `~/.opencode/opencode.json`:

stdio:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "bees": {
      "type": "local",
      "command": "bees",
      "args": ["serve", "--stdio"]
    }
  }
}
```

HTTP:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "bees": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "enabled": true,
      "oauth": false
    }
  }
}
```

Verify:

```bash
opencode mcp list
```

</details>

### Uninstall

```bash
# Remove CLI hooks (if installed)
bees setup claude cli --remove

# Remove MCP server (if installed). Use this to switch from stdio to http, as well
claude mcp remove bees

# Remove the package
pipx uninstall bees-md
```

## Advanced Usage

See [docs/advanced-usage.md](docs/advanced-usage.md) for full documentation on hives, ticket hierarchy, tags, statuses, eggs, queries, configuration, and more.
