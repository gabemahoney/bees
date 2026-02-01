# Deployment

This guide covers deploying and managing the bees MCP server in production and development environments.

## Background Process Options

To run the MCP server as a background process that persists after closing your terminal, you have several options:

### Using nohup (Unix/Linux/macOS)

```bash
cd /path/to/bees
nohup poetry run start-mcp > /dev/null 2>&1 &
```

This runs the server in the background and detaches it from your terminal session. The server will continue running even after you log out.

### Using screen (Unix/Linux/macOS)

```bash
screen -S bees-mcp
cd /path/to/bees
poetry run start-mcp
# Press Ctrl+A, then D to detach
```

Reattach later with: `screen -r bees-mcp`

### Using tmux (Unix/Linux/macOS)

```bash
tmux new -s bees-mcp
cd /path/to/bees
poetry run start-mcp
# Press Ctrl+B, then D to detach
```

Reattach later with: `tmux attach -t bees-mcp`

## Process Management

### Finding the Server Process

To find the bees MCP server process:

```bash
ps aux | grep "poetry run start-mcp"
```

Or to find processes using the HTTP port (default 8000):

```bash
lsof -i :8000
```

### Stopping the Server

**Graceful shutdown** (recommended):

```bash
kill <PID>
```

This sends a SIGTERM signal, allowing the server to clean up gracefully before shutting down.

**Force stop** (if graceful shutdown fails):

```bash
kill -9 <PID>
```

This immediately terminates the process without cleanup. Use only when necessary.

## Monitoring and Logs

### Log File Location

All server output is logged to `~/.bees/mcp.log`. Check this file for startup messages, errors, and operational details.

### Monitoring the Server

**Watch log file in real-time:**

```bash
tail -f ~/.bees/mcp.log
```

**Check if server process is running:**

```bash
ps aux | grep "poetry run start-mcp"
```

**Test server health endpoint:**

```bash
curl http://127.0.0.1:8000/health
```

**Check which process is using the port:**

```bash
lsof -i :8000
# or
netstat -an | grep 8000
```

## Production Considerations

### Systemd Service for Auto-Restart

For production deployments, consider creating a systemd service for automatic restarts:

```ini
[Unit]
Description=Bees MCP Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/bees
ExecStart=/usr/bin/poetry run start-mcp
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save to `/etc/systemd/system/bees-mcp.service` and enable with:

```bash
sudo systemctl enable bees-mcp
sudo systemctl start bees-mcp
```

### Logging Configuration

For production environments, consider:
- Log rotation to prevent disk space issues
- Centralized log aggregation for monitoring
- Appropriate log levels (INFO for production, DEBUG for troubleshooting)

### Security Considerations

**HTTP Port Exposure:**
- The default configuration binds to 127.0.0.1 (localhost only)
- Do NOT expose the HTTP port directly to the internet
- Use a reverse proxy (nginx, Apache) for external access
- Implement authentication at the reverse proxy level

**Firewall Rules:**
If external access is required:
- Restrict access by IP address
- Use VPN or SSH tunneling for remote connections
- Consider TLS termination at the reverse proxy

### Reverse Proxy Recommendations

Example nginx configuration:

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;

    # Add authentication
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```
