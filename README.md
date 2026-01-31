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

**Host Validation**: The host value is validated to ensure it's a valid IP address:
- **Valid formats**: IPv4 addresses (e.g., `127.0.0.1`, `0.0.0.0`) and IPv6 addresses (e.g., `::1`, `::`)
- **Security**: Only IP addresses are accepted - hostnames like `localhost` or domain names are rejected
- **Error handling**: Invalid hosts raise a clear `ValueError` with examples of valid formats

Examples of valid and invalid hosts:
- Valid: `127.0.0.1`, `0.0.0.0`, `192.168.1.1`, `::1`, `::`, `2001:db8::1`
- Invalid: `localhost`, `example.com`, `999.999.999.999`, `127.0.0.1:8000`, `192.168` (partial IP)

**Port Validation**: The port value is automatically validated during configuration loading:
- **Valid range**: 1 to 65535 (standard TCP/IP port range)
- **Type coercion**: String values from YAML (e.g., `"8000"`) are automatically converted to integers
- **Error handling**: Invalid ports (negative, zero, > 65535, or non-numeric strings) raise a clear
`ValueError` with details about the invalid value

Examples of valid and invalid ports:
- Valid: `1`, `8000`, `65535`, `"8080"` (coerced to integer)
- Invalid: `0`, `-1`, `65536`, `99999`, `"abc"`, `""`, `"8000.5"`

**Security Note**: The default host `127.0.0.1` ensures the server only accepts local connections,
preventing external access. This localhost binding is a deliberate security measure - the HTTP
server will reject connections from external machines. Only change this to `0.0.0.0` if you
understand the security implications and need external access.

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

**Monitoring the Server:**
```bash
# Watch log output in real-time
tail -f ~/.bees/mcp.log

# Check if server process is running
ps aux | grep start-mcp

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

#### Graceful Shutdown

The HTTP server implements graceful shutdown to ensure clean termination:

**Signal Handling:**
- Responds to SIGINT (Ctrl+C) and SIGTERM signals
- Signal handlers are registered *after* successful server initialization
- Handlers call `stop_server()` for cleanup but don't force immediate exit
- Relies on uvicorn's built-in shutdown mechanism to complete gracefully

**Shutdown Process:**
1. Signal received (SIGINT/SIGTERM)
2. Cleanup handler (`stop_server()`) called to close MCP resources
3. Uvicorn completes its shutdown sequence
4. All connections closed cleanly
5. Server exits without hanging or leaving resources open

This design prevents race conditions where signal handlers might be called before the server is
fully initialized, and ensures uvicorn has time to complete its shutdown procedures.

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
