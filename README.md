# Bees

A markdown-based ticket management system designed for LLMs.

## Overview

Bees is a markdown-based ticket management system designed specifically for LLM agents. It provides a simple, git-friendly way to track work through epics, tasks, and subtasks, making project management transparent and easily accessible to both humans and AI assistants. The system integrates with Claude Code via the Model Context Protocol (MCP), enabling seamless ticket management through conversation.

## Installation

Install dependencies using Poetry:

```bash
poetry install
```

Run the test suite to verify installation:

```bash
poetry run pytest
```

## MCP Server Setup

### Prerequisites

- Claude Code CLI installed
- Poetry installed
- This project's dependencies installed (`poetry install`)

### Configuration

Bees runs as an MCP server, so you need to configure it for Claude Code to access it. The `cwd`
(working directory) field is **required** because the server needs to find the bees project's
`config.yaml` and `tickets/` directory.

#### Configuration Management

Bees uses a centralized configuration module (`src/config.py`) that provides type-safe access to
settings through a `Config` object. The configuration is loaded from `config.yaml` at server
startup.

**Key features:**
- Type-safe attribute access: `config.http_host`, `config.http_port`, `config.ticket_directory`
- Nested schema support for logical grouping (e.g., `http.host`, `http.port`)
- Default values if config file is missing or incomplete
- Automatic validation and error reporting

The main server (`src/main.py`) imports and uses the `Config` class:

```python
from .config import Config, load_config

# Load configuration
config = load_config()

# Access settings via attributes
host = config.http_host         # Default: 127.0.0.1
port = config.http_port         # Default: 8000
tickets = config.ticket_directory  # Default: ./tickets
```

#### HTTP Transport Settings

Bees uses HTTP transport for MCP communication. The server configuration is defined in
`config.yaml`:

```yaml
# HTTP transport settings
http:
  # Server host address
  # Default: 127.0.0.1 (only accessible from this machine)
  # Set to 0.0.0.0 to allow external connections (not recommended for security)
  host: 127.0.0.1

  # Server port
  # Default: 8000
  # Valid range: 1-65535
  # Choose a port that's not in use by other services
  port: 8000
```

**Port Validation**: The port value is automatically validated during configuration loading:
- **Valid range**: 1 to 65535 (standard TCP/IP port range)
- **Type coercion**: String values from YAML (e.g., `"8000"`) are automatically converted to integers
- **Error handling**: Invalid ports (negative, zero, > 65535, or non-numeric strings) raise a clear
`ValueError` with details about the invalid value

Examples of valid and invalid ports:
- Valid: `1`, `8000`, `65535`, `"8080"` (coerced to integer)
- Invalid: `0`, `-1`, `65536`, `99999`, `"abc"`, `""`, `"8000.5"`

**Security Note**: The default host `127.0.0.1` ensures the server only accepts local connections,
preventing external access. Only change this to `0.0.0.0` if you understand the security
implications and need external access.

**Note**: The `claude mcp add` command does not automatically set `cwd` ([known issue](https://github.com/modelcontextprotocol/python-sdk/issues/1520)), so you must add it manually after running the command.

**Option A: User Scope (Available in All Projects)**

Use this if you want bees tools available across all your projects.

```bash
cd /path/to/bees/project
claude mcp add --scope user bees poetry run start-mcp
```

After running, manually add the `cwd` field to `~/.claude.json`:

```json
{
  "mcpServers": {
    "bees": {
      "command": "poetry",
      "args": ["run", "start-mcp"],
      "cwd": "/Users/yourname/projects/bees",
      "env": {}
    }
  }
}
```

**Option B: Local Scope (Single Project Only)**

Use this if you only want bees tools in one specific project.

From your target project directory:
```bash
cd /path/to/your/target-project
claude mcp add --scope local bees poetry run start-mcp
```

This creates an entry in `~/.claude.json` under your project's path. Now manually add the `cwd`
field to that project's `mcpServers` section. Find your project path in the file and add `cwd`:

```json
"/Users/yourname/projects/your-project": {
  "mcpServers": {
    "bees": {
      "command": "poetry",
      "args": ["run", "start-mcp"],
      "cwd": "/Users/yourname/projects/bees",  // ← Add this line
      "env": {}
    }
  }
}
```

**Important**:
- Replace paths with your actual directories
- The `cwd` field must point to the bees project directory
- Restart Claude Code after any configuration change

### Verify Installation

After restarting your Claude Code session, verify the MCP server is working:

1. Start a new Claude Code session
2. Ask Claude: "Can you use the bees health_check tool?"
3. Claude will call the tool and should report:
   ```json
   {"status": "healthy", "ready": true, ...}
   ```

Alternatively, check available MCP servers:
```bash
claude mcp list
```

You should see `bees` in the list of configured servers.

### Troubleshooting

**MCP tools not available:**
- Verify the `cwd` path in `~/.claude.json` is correct and absolute (not relative)
- Run `claude mcp list` to see configured servers
- Check Claude Code logs for error messages
- Ensure Poetry is in your PATH
- Start a new Claude Code session after config changes

**Connection errors:**
- Verify `config.yaml` exists in project root
- Check that ticket directories exist (`tickets/epics/`, `tickets/tasks/`,
  `tickets/subtasks/`)
- Run `poetry run start-mcp` manually to see detailed error messages

**Permission errors:**
- Ensure your user has read/write access to the ticket directories

## Usage

Once the MCP server is configured (see [MCP Server Setup](#mcp-server-setup)), you can
manage tickets through Claude Code.

### Creating Tickets

Create epics, tasks, and subtasks using the MCP server:

```python
# Use the bees_create_ticket tool from your MCP client
bees_create_ticket(
    title="Add user authentication",
    type="epic",
    description="Implement OAuth2 login flow"
)
```

### Running Queries

Search and filter tickets by status, type, or labels:

```python
# Use the bees_query_tickets tool to find open tasks
bees_query_tickets(status="open", type="task")
```

### Running the Linter

Validate your ticket database for consistency:

```bash
poetry run python -m src.cli lint
```

## Demo Dataset

Generate sample tickets for testing and development:

```bash
poetry run python scripts/generate_demo_tickets.py
```

This creates:
- 5 epics (auth system, dashboard, API core, docs, mobile app)
- 8 tasks with dependency chains
- 15 subtasks across various statuses

Use cases:
- Testing query and filter operations
- Validating dependency resolution logic
- Demonstrating ticket hierarchy and relationships
- Generating test data for linter validation

## Setting Up Your Project for Bees

To use bees in your project, create the following directory structure in your project root:

```
/your-project
  /tickets              # Ticket storage directory
    /epics              # Epic tickets go here
    /tasks              # Task tickets go here
    /subtasks           # Subtask tickets go here
```

The bees library expects this `/tickets` directory structure to exist in your current working
directory and will use it for all ticket read/write operations.

## Examples

[PLACEHOLDER: This section will contain practical usage examples and common workflows. Content
to be added in subsequent tasks.]
