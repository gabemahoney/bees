# Troubleshooting

This guide covers common issues you may encounter when using the Bees MCP server and
their solutions.

## Connection Issues

### MCP Tools Not Available

**Symptoms:**
- MCP tools don't appear in Claude Code
- Tools are unavailable even after configuration

**Solutions:**
- Ensure the bees HTTP server is running: `poetry run start-mcp`
- Run `claude mcp list` to verify connection shows `bees - ✓ Connected`
- Check server logs: `tail -f ~/.bees/mcp.log`
- Verify `~/.claude.json` has the HTTP transport configuration (see Quick Start in
  README)
- Start a new Claude Code session after config changes

### Connection Errors

**Symptoms:**
- Claude Code cannot connect to the MCP server
- Connection timeouts or refused connections

**Solutions:**
- Verify the server is listening: `lsof -i :8000` (macOS/Linux)
- Check `config.yaml` exists in project root
- Ensure ticket directories exist (`tickets/epics/`, `tickets/tasks/`,
  `tickets/subtasks/`)
- Review server logs for startup errors: `tail -f ~/.bees/mcp.log`

## Permission Issues

### Permission Errors

**Symptoms:**
- Cannot create, read, or update tickets
- File permission denied errors

**Solutions:**
- Ensure your user has read/write access to the ticket directories
- Check file permissions: `ls -la tickets/`
- Verify the server process has appropriate permissions

## HTTP Server Errors

### Port Already in Use

**Error Message:**
```
Failed to start server: Port 8000 is already in use
Please stop the other service using port 8000 or change the port in config.yaml
```

**Causes:**
- Another service is already using port 8000
- A previous server instance is still running

**Solutions:**
- Stop the other service using the port
- Or change the port in `config.yaml` to an available port number
- Find processes using the port: `lsof -i :8000` (macOS/Linux) or `netstat -ano |
  findstr :8000` (Windows)

### Permission Denied

**Error Message:**
```
Failed to start server: Permission denied for 127.0.0.1:80
Try using a port number above 1024 or run with appropriate permissions
```

**Causes:**
- Attempting to bind to a privileged port (below 1024)
- Insufficient permissions to bind to the requested port

**Solutions:**
- Use a port number above 1024 (e.g., 8000, 8080, 3000)
- Ports below 1024 require root/administrator privileges
- Never run the server as root - use a higher port number instead

### Invalid Bind Address

**Error Message:**
```
Failed to start server: Network error - [Errno 49] Can't assign requested address
Check that 127.0.0.1:8000 is a valid address
```

**Causes:**
- Invalid IP address in `config.yaml`
- Network interface not available

**Solutions:**
- Verify the `host` value in `config.yaml` is a valid IP address
- Use `127.0.0.1` for localhost (most common)
- Use `0.0.0.0` to bind to all interfaces (not recommended for security)

### Missing Dependencies

**Error Message:**
```
Failed to start server: Missing dependency - No module named 'uvicorn'
Please install required dependencies with: poetry install
```

**Causes:**
- Python dependencies not installed
- Virtual environment not activated
- Poetry not properly installed

**Solutions:**
- Run `poetry install` to install all required dependencies
- Verify you're running the command in the correct project directory
- Check that Poetry is properly installed: `poetry --version`

## Server Monitoring

### Checking Server Status

**Monitor server logs:**
```bash
tail -f ~/.bees/mcp.log
```

**Check server health:**
- The `health_check` tool reports server state
- Use this tool from Claude Code to verify the server is responding

**Verify server is running:**
- macOS/Linux: `lsof -i :8000`
- Windows: Check Task Manager or run `netstat -ano | findstr :8000`

### Debug Mode

For additional debugging information, check the server logs for detailed error
messages and stack traces.
