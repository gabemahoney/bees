---
id: features.bees-fo3
type: subtask
title: Document context fixtures (repo_root_ctx, mock_mcp_context)
description: 'Context: The context-related fixtures need clearer documentation about
  when to use each one.


  What to document:

  - Enhance repo_root_ctx docstring (already has good example, add more details)

  - Enhance mock_mcp_context docstring with comprehensive usage examples

  - Document mock_mcp_context''s create_mock_context factory function

  - Show example of using mock_mcp_context with MCP tool functions

  - Explain difference between repo_root_ctx (sets context) vs mock_mcp_context (mocks
  MCP)

  - Document when to use repo_root_ctx vs mock_mcp_context vs isolated_bees_env


  Files: tests/conftest.py (lines 207-264)


  Acceptance: Both docstrings include clear usage examples, explain differences between
  fixtures, and provide guidance on choosing the right fixture.'
parent: features.bees-m6i
created_at: '2026-02-05T08:09:53.184042'
updated_at: '2026-02-05T08:23:17.055619'
status: completed
bees_version: '1.1'
---

Context: The context-related fixtures need clearer documentation about when to use each one.

What to document:
- Enhance repo_root_ctx docstring (already has good example, add more details)
- Enhance mock_mcp_context docstring with comprehensive usage examples
- Document mock_mcp_context's create_mock_context factory function
- Show example of using mock_mcp_context with MCP tool functions
- Explain difference between repo_root_ctx (sets context) vs mock_mcp_context (mocks MCP)
- Document when to use repo_root_ctx vs mock_mcp_context vs isolated_bees_env

Files: tests/conftest.py (lines 207-264)

Acceptance: Both docstrings include clear usage examples, explain differences between fixtures, and provide guidance on choosing the right fixture.
