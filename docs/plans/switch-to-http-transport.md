# Plan: Switch MCP Server from stdio to HTTP Transport

## Problem Statement

The bees MCP server currently fails to connect to Claude Code when using stdio transport. The root cause is FastMCP's startup banner and logging output going to stderr, which interferes with the JSON-RPC communication over stdin/stdout.

### Current Issues

1. **FastMCP Banner Pollution**: FastMCP outputs an ASCII art banner to stderr on startup
2. **Pydantic Warning**: A pydantic JSON schema warning goes to stderr
3. **stdio Communication Interference**: Claude Code's MCP client uses stdin/stdout for JSON-RPC messages, and any stderr output disrupts the protocol handshake
4. **No Banner Suppression**: The `FASTMCP_NO_BANNER` environment variable doesn't work in FastMCP 2.14.4
5. **Connection Failure**: Claude Code shows "Failed to connect" despite the server starting successfully

### What We've Tried

- ✅ Moving Python logging to file (`~/.bees/mcp.log`) - helped but not enough
- ❌ Setting `FASTMCP_NO_BANNER=1` - environment variable not implemented
- ❌ Upgrading FastMCP - already on latest stable (2.14.4), beta has same issues
- ❌ Shell redirection in MCP config - complex and fragile

## Proposed Solution: HTTP Transport

Switch from stdio to HTTP transport, which completely avoids the stderr interference issue.

### Why HTTP Solves the Problem

| Aspect | stdio Transport | HTTP Transport |
|--------|----------------|----------------|
| **Communication** | stdin/stdout (single channel) | HTTP requests (network) |
| **Logging** | stderr interferes with JSON-RPC | stderr/stdout don't matter |
| **Banner** | Breaks protocol handshake | Shows harmlessly in server logs |
| **Separation** | All I/O mixed together | Clean separation of concerns |
| **Debugging** | Hard to debug connection issues | Easy to test with curl/browser |

### Advantages of HTTP

1. **Clean Separation**: Logs and communication use different channels
2. **Better Debugging**: Can test server with curl, view in browser
3. **Standard Protocol**: HTTP is well-understood and reliable
4. **No Startup Issues**: Server starts once and stays running
5. **Multiple Clients**: Can be accessed by multiple clients simultaneously
6. **Port Flexibility**: Can run on any available port

### Trade-offs

| Aspect | stdio | HTTP |
|--------|-------|------|
| **Startup** | Auto-started by Claude Code | Must start manually or via background service |
| **Port** | Not needed | Requires available port (default: 8000) |
| **Access** | Local only | Potentially network-accessible (use 127.0.0.1) |
| **Lifecycle** | Dies with Claude Code | Runs independently |

## Implementation Plan

### Step 1: Update Server Code

**File: `src/main.py`**

Change the `mcp.run()` call to use HTTP transport:

```python
# Old (line 167)
mcp.run()

# New
mcp.run(transport="http", host="127.0.0.1", port=8000)
```

**Rationale:**
- `transport="http"`: Use HTTP instead of stdio
- `host="127.0.0.1"`: Bind to localhost only (security)
- `port=8000`: Use port from config.yaml

### Step 2: Make Port Configurable

Read port from config.yaml that already exists:

```python
# In main() function, after loading config:
port = config.get('port', 8000)

# Pass to mcp.run()
mcp.run(transport="http", host="127.0.0.1", port=port)
```

### Step 3: Update Claude Code MCP Configuration

**File: `~/.claude.json`**

Replace the stdio configuration with HTTP:

```json
{
  "mcpServers": {
    "bees": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

**Note:** Remove the `command`, `args`, `cwd`, and `env` fields - not needed for HTTP transport.

### Step 4: Update README

**File: `README.md` - MCP Server Setup section**

Update instructions to reflect HTTP transport:

```markdown
## MCP Server Setup

### Start the Server

The bees MCP server uses HTTP transport. Start it in a separate terminal:

```bash
cd /path/to/bees
poetry run start-mcp
```

The server will start on http://127.0.0.1:8000/mcp

### Configure Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "bees": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Verify Connection

```bash
# Check server is running
curl http://127.0.0.1:8000/mcp

# Or in Claude Code
claude mcp list
# Should show: bees: http://127.0.0.1:8000/mcp - ✓ Connected
```
```

### Step 5: Consider Background Service (Optional)

For production use, consider running the server as a background service:

**Option A: systemd (Linux)**
**Option B: launchd (macOS)**
**Option C: Manual background process**

```bash
# Start in background
nohup poetry run start-mcp > ~/.bees/server.log 2>&1 &

# Save PID
echo $! > ~/.bees/server.pid

# Stop later
kill $(cat ~/.bees/server.pid)
```

## Testing Plan

### 1. Manual Server Testing

```bash
# Start server
cd /Users/gmahoney/projects/bees
poetry run start-mcp

# Expected output (in terminal or logs):
# - FastMCP banner (now harmless!)
# - "MCP Server is running..."
# - Server listening on 127.0.0.1:8000
```

### 2. HTTP Endpoint Testing

```bash
# Test server responds
curl http://127.0.0.1:8000/mcp

# Should return MCP server info (JSON response)
```

### 3. Claude Code Integration Testing

```bash
# Update ~/.claude.json with HTTP config
# Restart Claude Code
claude mcp list

# Expected: bees - ✓ Connected

# Test in Claude Code session:
> Can you use the bees health_check tool?

# Expected: Tool executes successfully
```

### 4. Functional Testing

Create test tickets to verify all MCP tools work:

```bash
# In Claude Code:
> Create an epic ticket titled "Test HTTP Transport"
> List all tickets
> Query for open epics
> Create a task under the epic
> Update the task status to in_progress
> Generate the ticket index
```

## Rollback Plan

If HTTP transport has issues:

1. Revert `src/main.py` changes (restore `mcp.run()`)
2. Revert `~/.claude.json` to stdio config
3. Server auto-starts via Claude Code again

Keep the logging-to-file changes - they're useful regardless of transport.

## Success Criteria

- ✅ Server starts without errors
- ✅ `claude mcp list` shows "✓ Connected"
- ✅ All MCP tools (health_check, create_ticket, query_tickets, etc.) work in Claude Code
- ✅ Server logs go to `~/.bees/mcp.log` (clean, not polluting anywhere)
- ✅ Can test server independently with curl
- ✅ README updated with correct instructions

## Future Considerations

### Authentication (Optional)

HTTP transport makes it easy to add authentication later:

```python
mcp.run(
    transport="http",
    host="127.0.0.1",
    port=8000,
    auth_token="your-secret-token"  # If FastMCP supports it
)
```

### Remote Access (Optional)

Could expose on network for team access:

```python
# ONLY if you want team access and understand security implications
mcp.run(
    transport="http",
    host="0.0.0.0",  # Listen on all interfaces
    port=8000
)
```

**Security Warning:** Don't expose without authentication!

## Timeline

- **Implementation**: 15 minutes (code changes + config update)
- **Testing**: 10 minutes (verify connection + basic tools)
- **Documentation**: 5 minutes (update README)
- **Total**: ~30 minutes

## References

- [FastMCP HTTP Transport Documentation](https://gofastmcp.com/deployment/running-server)
- [Claude Code MCP Configuration](https://code.claude.com/docs/en/mcp)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
