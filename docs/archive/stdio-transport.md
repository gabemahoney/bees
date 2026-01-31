# stdio Transport Configuration (Legacy)

**Note**: stdio transport is a legacy option. HTTP transport is now the recommended method for
connecting Claude Code to the bees MCP server. See the main README.md for HTTP configuration
instructions.

This document preserves stdio configuration instructions for users who need the legacy transport
option.

## stdio Transport Setup

**Note**: The `claude mcp add` command does not automatically set `cwd`
([known issue](https://github.com/modelcontextprotocol/python-sdk/issues/1520)), so you must add it
manually after running the command.

### Option A: User Scope (Available in All Projects)

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

### Option B: Local Scope (Single Project Only)

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
      "cwd": "/Users/yourname/projects/bees",
      "env": {}
    }
  }
}
```

### Important Notes

- Replace paths with your actual directories
- The `cwd` field must point to the bees project directory
- Restart Claude Code after any configuration change

## Verify Installation

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

You should see `bees - ✓ Connected` in the output.

## Why HTTP is Preferred

HTTP transport offers several advantages over stdio:
- Better reliability and error handling
- Support for concurrent connections
- Easier debugging and monitoring
- Standard REST-like interface

If you're currently using stdio transport, consider migrating to HTTP. See the main README.md for
HTTP configuration instructions.
