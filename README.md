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

### HTTP Server Overview

Bees runs as an HTTP-based MCP server for reliable, independent operation. When you start the
server with `poetry run start-mcp`, it:

1. Loads configuration from `config.yaml` (host, port, ticket directory)
2. Validates the ticket database for corruption
3. Initializes the HTTP server using uvicorn
4. Binds to `127.0.0.1` (localhost) by default for security
5. Listens on port `8000` (configurable)
6. Serves MCP tools over HTTP at `http://127.0.0.1:8000`

The server runs independently in its own process, staying available for multiple Claude Code
sessions. This HTTP transport eliminates stdio interference issues that can occur with
stdio-based MCP servers.

### Quick Start: HTTP Transport Configuration

**Recommended approach**: Use the example configuration file at `docs/examples/claude-config-http.json`
as your starting point. This file shows the correct HTTP transport format for the bees MCP server.

To configure Claude Code for HTTP transport:

1. Copy the `bees` object from `docs/examples/claude-config-http.json` into your `~/.claude.json`
   file under the `mcpServers` section
2. Ensure the bees HTTP server is running (see [Starting the Server](#starting-the-server) below)
3. Run `claude mcp list` to verify the connection shows `bees - ✓ Connected`

**Example HTTP configuration:**
```json
{
  "mcpServers": {
    "bees": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

**Key difference from stdio**: HTTP transport uses a simple `url` field instead of `command`,
`args`, `cwd`, and `env` fields. The server runs independently as a persistent process, making
it more reliable and supporting concurrent connections from multiple Claude Code sessions.

**Migrating from stdio?** See the [Migration Guide](docs/migration-guide.md) for step-by-step
instructions.

### Configuration

#### Configuration Management

Bees loads its configuration from `config.yaml` at server startup. Edit this file to customize server settings like HTTP host, port, and ticket directory location.

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

**Host**: Must be a valid IP address (IPv4 or IPv6). Use `127.0.0.1` for localhost (recommended for security) or `0.0.0.0` to allow external connections.

**Port**: Must be in range 1-65535. Use ports above 1024 to avoid needing elevated permissions.

#### Starting the Server

Start the HTTP server with:

```bash
cd /path/to/bees
poetry run start-mcp
```

The server will display startup information in its log file (`~/.bees/mcp.log`):

```
==============================================================
Bees MCP Server
==============================================================
Host: 127.0.0.1
Port: 8000
Ticket Directory: /path/to/tickets
==============================================================
Launching HTTP server on 127.0.0.1:8000...
MCP Server is running. Press Ctrl+C to stop.
```

**Note on Log Message Timing:**
The "Launching" message appears before the server starts accepting connections. This indicates
startup intention rather than completion, which is more accurate if the startup fails. Once
uvicorn successfully binds to the port and begins accepting connections, the server is fully
operational.

The server will continue running until you stop it with Ctrl+C.

#### Running as Background Process

To run the MCP server as a background process that persists after closing your terminal:

**Using nohup (Unix/Linux/macOS):**
```bash
cd /path/to/bees
nohup poetry run start-mcp > /dev/null 2>&1 &
```

This runs the server in the background and detaches it from your terminal session. The server will
continue running even after you log out.

**Using screen (Unix/Linux/macOS):**
```bash
screen -S bees-mcp
cd /path/to/bees
poetry run start-mcp
# Press Ctrl+A, then D to detach
```

Reattach later with: `screen -r bees-mcp`

**Using tmux (Unix/Linux/macOS):**
```bash
tmux new -s bees-mcp
cd /path/to/bees
poetry run start-mcp
# Press Ctrl+B, then D to detach
```

Reattach later with: `tmux attach -t bees-mcp`

**Log File Location:**
All server output is logged to `~/.bees/mcp.log`. Check this file for startup messages, errors, and
operational details.

**HTTP Endpoints:**

The server exposes the following HTTP endpoints:

- **`/mcp`** (POST) - MCP JSON-RPC protocol endpoint
  - Handles MCP tool execution via JSON-RPC 2.0 protocol
  - Provided by FastMCP framework
  - Example request:
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -d '{
        "jsonrpc": "2.0",
        "method": "health_check",
        "params": {},
        "id": 1
      }'
    ```

- **`/health`** (GET, POST) - Health check endpoint
  - Returns server health status and readiness information
  - Supports both GET and POST methods
  - Example request:
    ```bash
    curl http://127.0.0.1:8000/health
    ```
  - Example response:
    ```json
    {
      "status": "healthy",
      "server_running": true,
      "name": "Bees Ticket Management Server",
      "version": "0.1.0",
      "ready": true
    }
    ```

**Error Responses:**

All endpoints return JSON-formatted error responses with appropriate HTTP status codes:

- **400 Bad Request** - Invalid JSON or malformed request
  ```json
  {
    "jsonrpc": "2.0",
    "error": {
      "code": -32700,
      "message": "Parse error: Invalid JSON"
    },
    "id": null
  }
  ```

- **500 Internal Server Error** - Server-side error
  ```json
  {
    "status": "error",
    "message": "Error details here"
  }
  ```

**Monitoring the Server:**
```bash
# Watch log output in real-time
tail -f ~/.bees/mcp.log

# Check if server process is running
ps aux | grep start-mcp

# Test health endpoint
curl http://127.0.0.1:8000/health

# Check if port is in use (server is listening)
lsof -i :8000   # macOS/Linux
netstat -ano | findstr :8000   # Windows
```

**Stopping a Background Process:**
```bash
# Find the process ID
ps aux | grep start-mcp

# Stop the server gracefully
kill <PID>

# Force stop if needed (not recommended)
kill -9 <PID>
```

#### Connecting Claude Code

**RECOMMENDED: HTTP Transport**

HTTP transport is the preferred method for connecting Claude Code to the bees MCP server. It provides
better reliability and supports concurrent connections.

See the [Quick Start: HTTP Transport Configuration](#quick-start-http-transport-configuration) section
above for the HTTP configuration example. The example configuration file at
`docs/examples/claude-config-http.json` shows the correct format. Merge the `bees` entry from that
file into your `~/.claude.json` under the `mcpServers` section.

After updating your configuration, run `claude mcp list` to verify the connection shows "bees - ✓ Connected".

> **Note:** For legacy stdio transport configuration, see [docs/archive/stdio-transport.md](docs/archive/stdio-transport.md).

### HTTP Transport Testing & Verification

The HTTP transport configuration has been validated end-to-end and is ready for production use.
Testing confirmed:

**Connection Verification:**
1. Start the server: `poetry run start-mcp`
2. Verify server is listening: `lsof -i :8000`
3. Check connection status: `claude mcp list`
   - Expected output: `bees: http://127.0.0.1:8000/mcp (HTTP) - ✓ Connected`

**Tool Execution:**
- MCP tools execute successfully over HTTP transport
- Test with health check: `mcp__bees___health_check` returns server status
- No latency or stability issues observed

**Migration Validation:**
- HTTP transport provides equivalent functionality to stdio
- Cleaner server lifecycle management
- Supports concurrent Claude Code sessions
- No additional troubleshooting steps required

For detailed test results, see [docs/http-transport-test-report.md](docs/http-transport-test-report.md).

### Troubleshooting

**MCP tools not available:**
- Ensure the bees HTTP server is running: `poetry run start-mcp`
- Run `claude mcp list` to verify connection shows `bees - ✓ Connected`
- Check server logs: `tail -f ~/.bees/mcp.log`
- Verify `~/.claude.json` has the HTTP transport configuration (see [Quick Start](#quick-start-http-transport-configuration))
- Start a new Claude Code session after config changes

**Connection errors:**
- Verify the server is listening: `lsof -i :8000` (macOS/Linux)
- Check `config.yaml` exists in project root
- Ensure ticket directories exist (`tickets/epics/`, `tickets/tasks/`, `tickets/subtasks/`)
- Review server logs for startup errors: `tail -f ~/.bees/mcp.log`

**Permission errors:**
- Ensure your user has read/write access to the ticket directories

#### HTTP Server Error Scenarios

The server provides specific error messages for common HTTP problems:

**Port Already in Use:**
```
Failed to start server: Port 8000 is already in use
Please stop the other service using port 8000 or change the port in config.yaml
```
**Solution:**
- Stop the other service using the port
- Or change the port in `config.yaml` to an available port number
- Find processes using the port: `lsof -i :8000` (macOS/Linux) or `netstat -ano | findstr :8000`
(Windows)

**Permission Denied:**
```
Failed to start server: Permission denied for 127.0.0.1:80
Try using a port number above 1024 or run with appropriate permissions
```
**Solution:**
- Use a port number above 1024 (e.g., 8000, 8080, 3000)
- Ports below 1024 require root/administrator privileges
- Never run the server as root - use a higher port number instead

**Invalid Bind Address:**
```
Failed to start server: Network error - [Errno 49] Can't assign requested address
Check that 127.0.0.1:8000 is a valid address
```
**Solution:**
- Verify the `host` value in `config.yaml` is a valid IP address
- Use `127.0.0.1` for localhost (most common)
- Use `0.0.0.0` to bind to all interfaces (not recommended for security)

**Missing Dependencies:**
```
Failed to start server: Missing dependency - No module named 'uvicorn'
Please install required dependencies with: poetry install
```
**Solution:**
- Run `poetry install` to install all required dependencies
- Verify you're running the command in the correct project directory
- Check that Poetry is properly installed: `poetry --version`

**Server Monitoring:**
- Check server logs: `tail -f ~/.bees/mcp.log`
- Monitor server status: The health_check tool reports server state
- Verify server is running: `lsof -i :8000` (macOS/Linux) or check Task Manager (Windows)

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
