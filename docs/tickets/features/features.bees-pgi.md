---
id: features.bees-pgi
type: task
title: Fix test_mcp_server tool name test for new FastMCP convention
description: |
  Update test_tool_registration_count in test_mcp_server.py to match FastMCP's updated tool naming.
  
  **Problem:**
  Test at line 3136 expects old '- ' prefix convention that FastMCP used to add:
  ```python
  expected_tools = {'- health_check', '- create_ticket', ...}
  ```
  
  But FastMCP no longer adds the '- ' prefix to tool names.
  
  **Fix:**
  Update the expected_tools set to remove '- ' prefix from all tool names:
  ```python
  expected_tools = {'health_check', 'create_ticket', ...}
  ```
  
  **Files:**
  - tests/test_mcp_server.py (line ~3136)
  
  **Success criteria:**
  - Test test_tool_registration_count passes
  - Test correctly validates tool registration
  - No references to old '- ' prefix convention remain in test
parent: features.bees-nho
status: closed
priority: 2
labels: ["tests"]
created_at: '2026-02-05T07:01:00.000000'
updated_at: '2026-02-05T15:05:10.000000'
bees_version: '1.1'
---

Fix test to match FastMCP's updated tool naming convention (no '- ' prefix).
