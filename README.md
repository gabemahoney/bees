# Bees

A markdown-based ticket management system designed for LLMs.

## Overview

A markdown-based ticket management system for LLMs via Model Context Protocol.

## Installation

```bash
poetry install
poetry run pytest
```

## Quick Start

### Start the Server

Start the HTTP server with:

```bash
cd /path/to/bees
poetry run start-mcp
```

### Configure Claude Code

Add the following to your `~/.claude.json` under the `mcpServers` section:
```json
{
  "mcpServers": {
    "bees": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Verify Connection

```bash
claude mcp list
```

You should see `bees - ✓ Connected`.

## Usage

Manage tickets through Claude Code using the MCP tools. You can create epics, tasks, and subtasks, query tickets by status or type, update ticket properties, and generate markdown reports.

## Documentation

See docs/http-transport.md for HTTP transport architecture and configuration.
See docs/troubleshooting.md for common issues and solutions.
See docs/deployment.md for background process setup and server management.
See docs/integration.md for project setup, testing, and validation.
