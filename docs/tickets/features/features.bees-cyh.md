---
id: features.bees-cyh
type: task
title: Add explicit docstring documentation for _add_named_query and _generate_index
description: 'These two MCP tools don''t have the repo_root parameter (correctly),
  but docstrings should explicitly mention they use implicit path resolution to clarify
  why they differ from other MCP tools.


  File: src/mcp_server.py'
labels:
- documentation
up_dependencies:
- features.bees-lmo
parent: features.bees-h0a
children:
- features.bees-tva
- features.bees-tqs
created_at: '2026-02-03T12:35:29.010760'
updated_at: '2026-02-03T12:46:16.410817'
priority: 1
status: completed
bees_version: '1.1'
---

These two MCP tools don't have the repo_root parameter (correctly), but docstrings should explicitly mention they use implicit path resolution to clarify why they differ from other MCP tools.

File: src/mcp_server.py
