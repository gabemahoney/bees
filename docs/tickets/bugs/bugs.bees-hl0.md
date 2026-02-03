---
id: bugs.bees-hl0
type: task
title: Add integration test verifying tool naming pattern
description: 'Context: Need automated verification that server name change produces
  correct tool prefix pattern.


  What Needs to Change:

  - Add test that initializes MCP server and verifies exposed tool names

  - Test should check tools follow `mcp_bees_*` pattern

  - Test should fail if tools use `mcp______*` pattern


  Why: Prevent regression to old naming pattern in future changes.


  Success Criteria:

  - Test verifies all tools have `mcp_bees_` prefix

  - Test fails if incorrect prefix detected


  Files: tests/ (new test file)


  Epic: bugs.bees-itw'
parent: bugs.bees-itw
children:
- bugs.bees-763
- bugs.bees-jru
- bugs.bees-eo6
- bugs.bees-oig
- bugs.bees-8bp
created_at: '2026-02-03T07:21:22.149965'
updated_at: '2026-02-03T07:22:33.817183'
priority: 0
status: open
bees_version: '1.1'
---

Context: Need automated verification that server name change produces correct tool prefix pattern.

What Needs to Change:
- Add test that initializes MCP server and verifies exposed tool names
- Test should check tools follow `mcp_bees_*` pattern
- Test should fail if tools use `mcp______*` pattern

Why: Prevent regression to old naming pattern in future changes.

Success Criteria:
- Test verifies all tools have `mcp_bees_` prefix
- Test fails if incorrect prefix detected

Files: tests/ (new test file)

Epic: bugs.bees-itw
