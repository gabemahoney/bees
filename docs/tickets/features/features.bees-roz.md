---
id: features.bees-roz
type: task
title: Add optional repo_root parameter to _execute_freeform_query
description: "Add optional repo_root: str | None = None parameter to _execute_freeform_query()\
  \ MCP tool.\n\nWhat Needs to Change:\n- Add repo_root parameter to function signature\n\
  - If repo_root provided, use Path(repo_root) instead of get_repo_root(ctx)\n- If\
  \ repo_root not provided AND get_repo_root(ctx) returns None, raise ValueError:\n\
  \  \"Your client does not support Roots. Please provide your repo root using the\
  \ repo_root parameter.\"\n- Update docstring to document the repo_root parameter\n\
  \nFile: src/mcp_server.py"
labels:
- enhancement
status: open
created_at: '2026-02-03T16:39:58.037565'
updated_at: '2026-02-03T16:39:58.037569'
bees_version: '1.1'
parent: features.bees-h0a
priority: 0
---

Add optional repo_root: str | None = None parameter to _execute_freeform_query() MCP tool.

What Needs to Change:
- Add repo_root parameter to function signature
- If repo_root provided, use Path(repo_root) instead of get_repo_root(ctx)
- If repo_root not provided AND get_repo_root(ctx) returns None, raise ValueError:
  "Your client does not support Roots. Please provide your repo root using the repo_root parameter."
- Update docstring to document the repo_root parameter

File: src/mcp_server.py
