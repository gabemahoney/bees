---
id: features.bees-w43
type: epic
title: Convert bees MCP server to HTTP/SSE transport for shared persistent instance
description: "## Problem\n\nCurrently, bees MCP server uses **stdio transport**, which\
  \ means:\n- Each Claude Code session spawns its own server process (1:1 connection)\n\
  - Code changes require restarting all Claude Code sessions\n- No shared state between\
  \ sessions\n- Inefficient for development and multi-session workflows\n\n## Proposed\
  \ Solution\n\nConvert bees MCP server to use **HTTP transport** (SSE or Streamable\
  \ HTTP) to enable:\n- One persistent server process serving multiple clients\n-\
  \ Hot reload: restart just the MCP server without restarting Claude Code sessions\n\
  - Shared state across all connections\n- Stateful Singleton Server pattern: one\
  \ shared McpServer instance with lightweight transports per client\n\n## Architecture\
  \ Options\n\n### Option 1: SSE Transport (Server-Sent Events)\n- HTTP POST for client-to-server\
  \ messages\n- SSE for server-to-client streaming\n- Supported since MCP 1.0\n- Good\
  \ for moderate concurrency\n\n### Option 2: Streamable HTTP Transport (Recommended\
  \ for 2026)\n- Modern standard (released March 2025)\n- Better for serverless/auto-scaling\n\
  - HTTP/2 multiplexing for hundreds of concurrent streams\n- Session state can be\
  \ externalized (Redis, DynamoDB)\n\n## Implementation Requirements\n\n1. **Server\
  \ Side**: Update bees MCP server to listen on HTTP endpoint\n   - Choose port (e.g.,\
  \ http://localhost:3000)\n   - Implement SSE or Streamable HTTP transport\n   -\
  \ Add health check endpoint\n   - Support graceful shutdown and restart\n\n2. **Client\
  \ Side**: Update Claude Code MCP configuration\n   - Change from stdio to HTTP transport\
  \ in ~/.claude.json\n   - Configure endpoint URL\n   - Handle connection failures\
  \ gracefully\n\n3. **Development Workflow**: Enable hot reload\n   - Restart script\
  \ for just the MCP server\n   - File watcher for automatic restarts on code changes\
  \ (optional)\n   - Clear error messages when server is down\n\n## Benefits\n\n-\
  \ **Faster development**: Change code, restart server, continue session\n- **Shared\
  \ state**: All sessions see the same ticket data\n- **Better performance**: One\
  \ process vs N processes for N sessions\n- **Production ready**: Can deploy as persistent\
  \ service\n\n## Success Criteria\n\n- Single bees MCP server process runs persistently\n\
  - Multiple Claude Code sessions can connect simultaneously\n- Restarting MCP server\
  \ doesn't require restarting Claude Code sessions\n- All existing MCP tools work\
  \ identically (no breaking changes)\n- Configuration documented in README with examples\n\
  \n## References\n\n- [MCP Server Transports: STDIO, Streamable HTTP & SSE](https://docs.roocode.com/features/mcp/server-transports)\n\
  - [Configure MCP Servers for Multiple Connections](https://mcpcat.io/guides/configuring-mcp-servers-multiple-simultaneous-connections/)\n\
  - [Transports - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)"
labels:
- enhancement
- mcp
- transport
status: open
created_at: '2026-02-03T12:04:15.520903'
updated_at: '2026-02-03T12:04:15.520906'
bees_version: '1.1'
priority: 2
---

## Problem

Currently, bees MCP server uses **stdio transport**, which means:
- Each Claude Code session spawns its own server process (1:1 connection)
- Code changes require restarting all Claude Code sessions
- No shared state between sessions
- Inefficient for development and multi-session workflows

## Proposed Solution

Convert bees MCP server to use **HTTP transport** (SSE or Streamable HTTP) to enable:
- One persistent server process serving multiple clients
- Hot reload: restart just the MCP server without restarting Claude Code sessions
- Shared state across all connections
- Stateful Singleton Server pattern: one shared McpServer instance with lightweight transports per client

## Architecture Options

### Option 1: SSE Transport (Server-Sent Events)
- HTTP POST for client-to-server messages
- SSE for server-to-client streaming
- Supported since MCP 1.0
- Good for moderate concurrency

### Option 2: Streamable HTTP Transport (Recommended for 2026)
- Modern standard (released March 2025)
- Better for serverless/auto-scaling
- HTTP/2 multiplexing for hundreds of concurrent streams
- Session state can be externalized (Redis, DynamoDB)

## Implementation Requirements

1. **Server Side**: Update bees MCP server to listen on HTTP endpoint
   - Choose port (e.g., http://localhost:3000)
   - Implement SSE or Streamable HTTP transport
   - Add health check endpoint
   - Support graceful shutdown and restart

2. **Client Side**: Update Claude Code MCP configuration
   - Change from stdio to HTTP transport in ~/.claude.json
   - Configure endpoint URL
   - Handle connection failures gracefully

3. **Development Workflow**: Enable hot reload
   - Restart script for just the MCP server
   - File watcher for automatic restarts on code changes (optional)
   - Clear error messages when server is down

## Benefits

- **Faster development**: Change code, restart server, continue session
- **Shared state**: All sessions see the same ticket data
- **Better performance**: One process vs N processes for N sessions
- **Production ready**: Can deploy as persistent service

## Success Criteria

- Single bees MCP server process runs persistently
- Multiple Claude Code sessions can connect simultaneously
- Restarting MCP server doesn't require restarting Claude Code sessions
- All existing MCP tools work identically (no breaking changes)
- Configuration documented in README with examples

## References

- [MCP Server Transports: STDIO, Streamable HTTP & SSE](https://docs.roocode.com/features/mcp/server-transports)
- [Configure MCP Servers for Multiple Connections](https://mcpcat.io/guides/configuring-mcp-servers-multiple-simultaneous-connections/)
- [Transports - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
