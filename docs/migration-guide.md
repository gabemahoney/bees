# Bees MCP Server Configuration Migration Guide

## Overview

This guide helps you migrate your bees MCP server configuration from stdio transport to HTTP
transport. The HTTP transport provides more reliable communication between Claude Code and the
bees server by avoiding stdio interference issues that can occur with stderr output from FastMCP
and other libraries.

**Why HTTP is more reliable:**
- **Clean separation**: Server logs and MCP communication use different channels
- **No stderr interference**: FastMCP's startup banner and warnings don't disrupt the protocol
- **Better debugging**: Test the server independently with curl or your browser
- **Persistent server**: Runs independently as a long-lived process

The migration involves removing stdio-specific fields (command, args, cwd, env) from your
~/.claude.json configuration and replacing them with a simple HTTP URL pointing to
http://127.0.0.1:8000/mcp.

## Prerequisites

Before starting the migration, ensure you have:

- **Bees MCP server installed**: The bees project should be set up on your machine
- **Python and Poetry**: Required to run the bees server (`poetry run start-mcp`)
- **Existing stdio configuration**: You should have a working stdio configuration in
  ~/.claude.json that you want to migrate
- **Claude Code CLI**: The `claude` command should be available in your terminal

If you don't have bees installed yet, see the main [README.md](../README.md) for installation
instructions.

## Migration Steps

Follow these steps to migrate from stdio to HTTP transport:

### 1. Start the HTTP Server

**Before** making configuration changes, start the HTTP server in a separate terminal:

```bash
cd /path/to/bees
poetry run start-mcp
```

The server should display startup information and begin listening on `http://127.0.0.1:8000`.
Keep this terminal open - the server must run continuously for Claude Code to connect.

### 2. Stop Any Running Claude Code Sessions

If you have Claude Code running with the old stdio configuration, close those sessions. This
ensures a clean transition to the new configuration.

### 3. Open Your Configuration File

Open `~/.claude.json` in your text editor:

```bash
# macOS/Linux
nano ~/.claude.json
# or
vim ~/.claude.json
# or
code ~/.claude.json

# Windows
notepad %USERPROFILE%\.claude.json
```

### 4. Locate the Bees Server Configuration

Find the `bees` entry under the `mcpServers` section. It should look like this:

```json
{
  "mcpServers": {
    "bees": {
      "command": "poetry",
      "args": ["run", "start-mcp"],
      "cwd": "/Users/yourname/projects/bees",
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

### 5. Remove stdio-Specific Fields

Delete the following fields from the bees configuration:
- `command`
- `args`
- `cwd`
- `env`

### 6. Add the HTTP URL Field

Replace the deleted fields with a single `url` field:

```json
{
  "mcpServers": {
    "bees": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### 7. Save the Configuration File

Save `~/.claude.json` and close your editor.

### 8. Verify the Connection

Test that Claude Code can connect to the HTTP server:

```bash
claude mcp list
```

You should see:
```
bees - ✓ Connected
```

If you see an error, proceed to the [Troubleshooting](#troubleshooting) section below.

### Common Mistakes to Avoid

**Wrong URL format:**
- ✅ Correct: `"url": "http://127.0.0.1:8000/mcp"`
- ❌ Wrong: `"url": "127.0.0.1:8000"` (missing http:// and /mcp)
- ❌ Wrong: `"url": "http://localhost:8000/mcp"` (use 127.0.0.1 instead)

**Forgetting to start the server:**
- The HTTP server must be running **before** Claude Code tries to connect
- Start it with `poetry run start-mcp` in a separate terminal
- The server won't auto-start like stdio transport did

**JSON syntax errors:**
- Ensure proper comma placement between fields
- Use double quotes for strings, not single quotes
- Validate your JSON with an online validator if needed

**Wrong port:**
- If you changed the port in `config.yaml`, update the URL accordingly
- Example: If port is 8080, use `"url": "http://127.0.0.1:8080/mcp"`

## Before/After Examples

### Before: stdio Transport Configuration

The old stdio configuration used command-line execution to start the server process:

```json
{
  "mcpServers": {
    "bees": {
      "command": "poetry",
      "args": ["run", "start-mcp"],
      "cwd": "/Users/yourname/projects/bees",
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

**Key characteristics of stdio transport:**
- `command`: Executable that starts the server (poetry)
- `args`: Command-line arguments passed to poetry
- `cwd`: Working directory (required for finding config.yaml and tickets/)
- `env`: Environment variables passed to the server process
- Server auto-starts when Claude Code needs it
- Server terminates when Claude Code closes

### After: HTTP Transport Configuration

The new HTTP configuration uses a simple URL endpoint:

```json
{
  "mcpServers": {
    "bees": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

**Key characteristics of HTTP transport:**
- `url`: HTTP endpoint where the server is listening
- No command/args/cwd/env fields needed
- Server must be started manually before connecting (`poetry run start-mcp`)
- Server runs independently as a persistent process
- Multiple Claude Code sessions can connect simultaneously

### Full ~/.claude.json Examples

**Before (stdio):**
```json
{
  "mcpServers": {
    "bees": {
      "command": "poetry",
      "args": ["run", "start-mcp"],
      "cwd": "/Users/yourname/projects/bees",
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

**After (HTTP):**
```json
{
  "mcpServers": {
    "bees": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

> **Note:** The HTTP configuration is much simpler and doesn't require specifying the project
> path, since the server loads its configuration from config.yaml at startup.

## Troubleshooting

### Connection Refused Error

**Symptom:**
```
bees - ✗ Not Connected
Error: Connection refused
```

**Cause:** The HTTP server is not running or not listening on the expected port.

**Solution:**
1. Check if the server is running:
   ```bash
   # macOS/Linux
   lsof -i :8000

   # Windows
   netstat -ano | findstr :8000
   ```

2. If no output, start the server:
   ```bash
   cd /path/to/bees
   poetry run start-mcp
   ```

3. Verify server logs at `~/.bees/mcp.log` for error messages

4. If the port is in use by another service, change it in `config.yaml`:
   ```yaml
   http:
     port: 8080  # Use a different port
   ```
   Then update your `~/.claude.json` URL to match the new port.

### "bees - ✗ Not Connected" (Generic)

**Symptom:**
```
bees - ✗ Not Connected
```

**Cause:** Wrong URL or port in configuration.

**Solution:**
1. Verify the URL in `~/.claude.json` matches the server configuration:
   - Check `config.yaml` for the correct port (default: 8000)
   - Ensure URL format is: `"url": "http://127.0.0.1:8000/mcp"`
   - Note the `/mcp` endpoint suffix is required

2. Test the server directly with curl:
   ```bash
   curl http://127.0.0.1:8000/health
   ```

   Expected response:
   ```json
   {
     "status": "healthy",
     "server_running": true,
     "ready": true
   }
   ```

3. If curl fails, the server isn't running or the port is wrong

### Invalid JSON Syntax Error

**Symptom:**
```
Error parsing ~/.claude.json: Unexpected token
```

**Cause:** Syntax error in the JSON configuration file.

**Solution:**
1. Validate your JSON syntax:
   - Use an online JSON validator (paste your `~/.claude.json` contents)
   - Check for missing commas, quotes, or brackets
   - Ensure proper nesting and closing of objects

2. Common JSON mistakes:
   ```json
   // ❌ Wrong: Single quotes
   { 'url': 'http://127.0.0.1:8000/mcp' }

   // ✅ Correct: Double quotes
   { "url": "http://127.0.0.1:8000/mcp" }

   // ❌ Wrong: Missing comma
   {
     "bees": { "url": "..." }
     "other": { "url": "..." }
   }

   // ✅ Correct: Comma between entries
   {
     "bees": { "url": "..." },
     "other": { "url": "..." }
   }
   ```

3. Restore from backup if needed:
   ```bash
   # macOS/Linux
   cp ~/.claude.json.backup ~/.claude.json
   ```

### "command not found" Error Persists

**Symptom:**
Old stdio behavior continues, or errors mention the `poetry` command.

**Cause:** Old stdio configuration still present in `~/.claude.json`.

**Solution:**
1. Open `~/.claude.json` and verify the bees configuration:
   ```json
   {
     "mcpServers": {
       "bees": {
         "url": "http://127.0.0.1:8000/mcp"
       }
     }
   }
   ```

2. Ensure **all** stdio-specific fields are removed:
   - `command` - should be deleted
   - `args` - should be deleted
   - `cwd` - should be deleted
   - `env` - should be deleted

3. Only the `url` field should remain in the bees configuration

4. Save the file and restart Claude Code

### Server Starts But Claude Code Can't Connect

**Symptom:**
Server logs show it's running, but `claude mcp list` shows "✗ Not Connected".

**Cause:** Mismatch between server configuration and Claude Code URL.

**Solution:**
1. Check the server startup logs in `~/.bees/mcp.log`:
   ```
   Host: 127.0.0.1
   Port: 8000
   ```

2. Verify your `~/.claude.json` URL matches:
   ```json
   {
     "url": "http://127.0.0.1:8000/mcp"
   }
   ```

3. Test the MCP endpoint directly:
   ```bash
   curl -X POST http://127.0.0.1:8000/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"health_check","params":{},"id":1}'
   ```

   Should return a JSON response with server health information.

4. If curl works but Claude Code doesn't, restart Claude Code completely

### Port Already in Use

**Symptom:**
```
Failed to start server: Port 8000 is already in use
```

**Cause:** Another process is using port 8000.

**Solution:**
1. Find the process using the port:
   ```bash
   # macOS/Linux
   lsof -i :8000

   # Windows
   netstat -ano | findstr :8000
   ```

2. Either:
   - **Option A:** Stop the other process using port 8000
   - **Option B:** Change bees to use a different port

   For Option B, edit `config.yaml`:
   ```yaml
   http:
     port: 8080  # Use a different port
   ```

   Then update `~/.claude.json`:
   ```json
   {
     "url": "http://127.0.0.1:8080/mcp"
   }
   ```

### General Diagnostic Commands

When troubleshooting, these commands are helpful:

```bash
# Check if server is running
ps aux | grep start-mcp

# View server logs in real-time
tail -f ~/.bees/mcp.log

# Test server health endpoint
curl http://127.0.0.1:8000/health

# Verify Claude Code configuration
cat ~/.claude.json | grep -A 5 "bees"

# List all MCP servers configured
claude mcp list
```

## Verification

After completing the migration, follow these steps to verify everything works correctly.

### Step 1: Start the MCP Server

In a separate terminal, start the HTTP server:

```bash
cd /path/to/bees
poetry run start-mcp
```

**Expected output** (in `~/.bees/mcp.log`):
```
==============================================================
Bees MCP Server
==============================================================
Host: 127.0.0.1
Port: 8000
Ticket Directory: /path/to/bees/tickets
==============================================================
Launching HTTP server on 127.0.0.1:8000...
MCP Server is running. Press Ctrl+C to stop.
```

**Success indicator:** The server starts without errors and displays the "MCP Server is running"
message.

### Step 2: Check Connection Status

Run the Claude Code MCP list command:

```bash
claude mcp list
```

**Expected output:**
```
bees - ✓ Connected
```

**Success indicator:** The checkmark (✓) indicates successful connection. If you see "✗ Not
Connected", refer to the [Troubleshooting](#troubleshooting) section.

### Step 3: Test HTTP Health Endpoint

Verify the server responds to direct HTTP requests:

```bash
curl http://127.0.0.1:8000/health
```

**Expected output:**
```json
{
  "status": "healthy",
  "server_running": true,
  "name": "Bees Ticket Management Server",
  "version": "0.1.0",
  "ready": true
}
```

**Success indicator:** Server returns a JSON response with `"status": "healthy"` and
`"ready": true`.

### Step 4: Test MCP Tool Execution

Start a Claude Code session and test an MCP tool:

```bash
claude
```

Then in the Claude Code session, ask Claude to use a bees tool:

```
Can you use the bees health_check tool?
```

**Expected behavior:**
- Claude successfully calls the `mcp__bees___health_check` tool
- Tool returns health status information
- No connection errors or tool execution failures

**Example successful response:**
```
The bees MCP server is healthy and running correctly.
Server status: healthy
Ready: true
```

### Step 5: Create a Test Ticket (Optional)

For thorough verification, test ticket creation:

```
Create an epic ticket titled "Test HTTP Transport Migration"
```

**Expected behavior:**
- Claude calls the `mcp__bees___create_ticket` tool
- Tool creates a new epic ticket
- Returns the ticket ID and confirmation

**Example successful response:**
```
Created epic ticket: bees-xyz123
Title: Test HTTP Transport Migration
```

You can verify the ticket was created by checking the `tickets/epics/` directory or asking Claude
to list all epics.

### Step 6: Verify Concurrent Connections (Optional)

HTTP transport supports multiple simultaneous connections. To test:

1. Keep your first Claude Code session open
2. Start a second Claude Code session in another terminal:
   ```bash
   claude
   ```
3. In the second session, use a bees tool (e.g., health_check)

**Expected behavior:**
- Both sessions can use bees tools simultaneously
- No connection conflicts or errors
- Server continues running and serving both clients

**Success indicator:** Multiple Claude Code sessions can access the MCP server concurrently without
interference.

### Migration Complete!

If all verification steps pass, your migration is complete and successful. The bees MCP server is
now running on HTTP transport with improved reliability and debugging capabilities.

**Benefits you now have:**
- No more stderr interference from FastMCP banner or warnings
- Can test server independently with curl or browser
- Server persists across Claude Code sessions
- Support for concurrent connections
- Cleaner separation between server logs and MCP communication

**Next steps:**
- Consider running the server as a background process (see README.md)
- Bookmark the health endpoint for quick server status checks: http://127.0.0.1:8000/health
- Monitor server logs at `~/.bees/mcp.log` for any issues
