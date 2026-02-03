---
id: features.bees-1uj
type: subtask
title: Update all @mcp.tool() decorators to call extracted module functions
description: "Context: Tool decorators should be thin wrappers that delegate to the\
  \ extracted modules.\n\nWhat to Do:\n- Update each @mcp.tool() decorator to call\
  \ the corresponding function from the extracted module\n- Pass through all parameters\
  \ correctly\n- Preserve return values\n- Ensure all tool names remain unchanged\n\
  - Examples:\n  - @mcp.tool() def _create_ticket(...) -> should call mcp_ticket_ops._create_ticket(...)\n\
  \  - @mcp.tool() def _colonize_hive(...) -> should call mcp_hive_ops._colonize_hive(...)\n\
  \  - @mcp.tool() def _execute_query(...) -> should call mcp_query_ops._execute_query(...)\n\
  \nFiles: src/mcp_server.py\n\nAcceptance: All tool decorators are 2-3 line wrappers\
  \ that delegate to extracted modules. All parameters and return values are correctly\
  \ passed through."
parent: features.bees-4u5
status: open
created_at: '2026-02-03T17:03:21.508701'
updated_at: '2026-02-03T17:03:21.508704'
bees_version: '1.1'
---

Context: Tool decorators should be thin wrappers that delegate to the extracted modules.

What to Do:
- Update each @mcp.tool() decorator to call the corresponding function from the extracted module
- Pass through all parameters correctly
- Preserve return values
- Ensure all tool names remain unchanged
- Examples:
  - @mcp.tool() def _create_ticket(...) -> should call mcp_ticket_ops._create_ticket(...)
  - @mcp.tool() def _colonize_hive(...) -> should call mcp_hive_ops._colonize_hive(...)
  - @mcp.tool() def _execute_query(...) -> should call mcp_query_ops._execute_query(...)

Files: src/mcp_server.py

Acceptance: All tool decorators are 2-3 line wrappers that delegate to extracted modules. All parameters and return values are correctly passed through.
