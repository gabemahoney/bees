---
id: features.bees-4f3
type: task
title: Fix 42 failing tests after removing Path.cwd() fallback
description: 'After removing Path.cwd() fallback in task features.bees-3p6, 42 tests
  are failing because they don''t properly provide repo_root through the call chain.


  Test failures found by code-review:

  1. test_mcp_roots.py - Tests passing repo_root= parameter incorrectly to MCP functions

  2. test_mcp_server.py::TestListHives - 8 tests missing proper context object


  Current test results: 1164 passed, 42 failed


  What Needs to Change:

  - Fix all 42 failing tests to properly pass repo_root through call chains

  - Update Mock context objects where needed

  - Run full test suite to achieve 100% pass rate


  File: tests/test_mcp_roots.py, tests/test_mcp_server.py'
labels:
- bug
up_dependencies:
- features.bees-3p6
down_dependencies:
- features.bees-wen
parent: features.bees-h0a
created_at: '2026-02-03T16:11:49.698627'
updated_at: '2026-02-03T16:22:02.578535'
priority: 1
status: open
bees_version: '1.1'
---

After removing Path.cwd() fallback in task features.bees-3p6, 42 tests are failing because they don't properly provide repo_root through the call chain.

Test failures found by code-review:
1. test_mcp_roots.py - Tests passing repo_root= parameter incorrectly to MCP functions
2. test_mcp_server.py::TestListHives - 8 tests missing proper context object

Current test results: 1164 passed, 42 failed

What Needs to Change:
- Fix all 42 failing tests to properly pass repo_root through call chains
- Update Mock context objects where needed
- Run full test suite to achieve 100% pass rate

File: tests/test_mcp_roots.py, tests/test_mcp_server.py
