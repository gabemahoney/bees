---
id: features.bees-pgf6
type: subtask
title: Document or fix FastMCP tool naming issue (test_mcp_server.py)
description: |
  Resolve 1 skipped test in test_mcp_server.py for FastMCP tool naming behavior.
  
  Test: test_tool_registration_count (line 3108)
  Skip reason: "Tool names have '- ' prefix issue - known issue with FastMCP tool naming"
  
  The test expects a specific count of registered tools, but FastMCP adds unexpected prefixes to tool names.
  
  Decision needed: Is this our bug or a FastMCP limitation?
  
  **Option A**: Fix our tool naming
  - Investigate if we're causing the '- ' prefix
  - Fix our MCP tool registration code
  - Update test to pass
  
  **Option B**: Work around FastMCP issue
  - If this is a FastMCP bug we can't control
  - Update test to expect the prefixed names
  - Document the workaround
  
  **Option C**: Accept limitation and improve skip documentation
  - If we can't fix it and it doesn't impact functionality
  - Add clear documentation about why this is skipped
  - Maybe file an issue with FastMCP project
  
  Action: Investigate root cause and either fix, work around, or document clearly.
parent: features.bees-pgf
status: completed
priority: 3
created_at: '2026-02-05T05:40:00.000000'
updated_at: '2026-02-05T05:40:00.000000'
bees_version: '1.1'
---

Investigate and resolve FastMCP tool naming issue.
