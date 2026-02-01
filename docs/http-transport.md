# HTTP Transport

This document provides detailed information about the HTTP transport implementation
in Bees MCP server.

## Architecture Overview

Bees runs as an HTTP-based MCP server for reliable, independent operation. When you
start the server with `poetry run start-mcp`, it:

1. Loads configuration from `config.yaml` (host, port, ticket directory)
2. Validates the ticket database for corruption
3. Initializes the HTTP server using uvicorn
4. Binds to `127.0.0.1` (localhost) by default for security
5. Listens on port `8000` (configurable)
6. Serves MCP tools over HTTP at `http://127.0.0.1:8000`

The server runs independently in its own process, staying available for multiple
Claude Code sessions. This HTTP transport eliminates stdio interference issues
that can occur with stdio-based MCP servers.

## Configuration Reference

Bees uses HTTP transport for MCP communication. The server configuration is
defined in `config.yaml`:

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

**Host**: Must be a valid IP address (IPv4 or IPv6). Use `127.0.0.1` for
localhost (recommended for security) or `0.0.0.0` to allow external connections.

**Port**: Must be in range 1-65535. Use ports above 1024 to avoid needing
elevated permissions.

## API Endpoints

The server exposes the following HTTP endpoints:

### `/mcp` (POST) - MCP JSON-RPC protocol endpoint

Handles MCP tool execution via JSON-RPC 2.0 protocol. Provided by FastMCP
framework.

**Example request:**
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

### `/health` (GET, POST) - Health check endpoint

Returns server health status and readiness information. Supports both GET and
POST methods.

**Example request:**
```bash
curl http://127.0.0.1:8000/health
```

**Example response:**
```json
{
  "status": "healthy",
  "server_running": true,
  "name": "Bees Ticket Management Server",
  "version": "0.1.0",
  "ready": true
}
```

### Error Responses

All endpoints return JSON-formatted error responses with appropriate HTTP status
codes:

**400 Bad Request** - Invalid JSON or malformed request:
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

**500 Internal Server Error** - Server-side error:
```json
{
  "status": "error",
  "message": "Error details here"
}
```

## Testing and Validation

The HTTP transport configuration has been validated end-to-end and is ready for
production use. Testing confirmed:

### Connection Verification

1. Start the server: `poetry run start-mcp`
2. Verify server is listening: `lsof -i :8000`
3. Check connection status: `claude mcp list`
   - Expected output: `bees: http://127.0.0.1:8000/mcp (HTTP) - ✓ Connected`

### Tool Execution

- MCP tools execute successfully over HTTP transport
- Test with health check: `mcp__bees___health_check` returns server status
- No latency or stability issues observed

### Migration Validation

- HTTP transport provides equivalent functionality to stdio
- Cleaner server lifecycle management
- Supports concurrent Claude Code sessions
- No additional troubleshooting steps required

For detailed test results, see
[docs/http-transport-test-report.md](docs/http-transport-test-report.md).
