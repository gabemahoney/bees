---
id: features.bees-aa2
type: task
title: Update MCP entry points with context management
description: |
  Context: MCP entry points are the boundary where repo_root enters the system. They need to set context once via repo_root_context(), then all downstream calls read from it. This task establishes the clean boundary pattern.

  What Needs to Change:
  - Update ~15 entry points in mcp_ticket_ops.py, mcp_hive_ops.py, mcp_query_ops.py, mcp_index_ops.py
  - Keep `repo_root: str | None = None` parameter as explicit fallback for non-Roots clients
  - Create helper function `resolve_repo_root(ctx, explicit_root)` in mcp_repo_utils.py that tries Roots protocol first, then falls back to explicit_root
  - Wrap each entry point's function body with `with repo_root_context(resolved_root):`
  - Remove repo_root parameter from all downstream function calls within entry points
  - Fix existing bug at mcp_ticket_ops.py:441 where _update_ticket uses repo_root before defining it

  Why: Sets up clean architectural boundary - context set once at entry, read everywhere downstream. This eliminates the parameter threading problem.

  Files: src/mcp_ticket_ops.py, src/mcp_hive_ops.py, src/mcp_query_ops.py, src/mcp_index_ops.py, src/mcp_repo_utils.py

  Note: See parent Epic features.bees-nho for detailed implementation patterns and code examples.

  Success Criteria:
  - All entry points use repo_root_context() wrapper
  - Optional repo_root param works for non-Roots clients
  - resolve_repo_root() helper exists and handles both Roots and explicit param
  - Bug at mcp_ticket_ops.py:441 is fixed
  - No repo_root parameters passed to downstream calls
parent: features.bees-nho
children: ["features.bees-ab4", "features.bees-ab5", "features.bees-ab6", "features.bees-ab7", "features.bees-ab8", "features.bees-ab9", "features.bees-aba"]
status: completed
priority: 0
up_dependencies: ["features.bees-aa1"]
created_at: '2026-02-04T19:00:01.000000'
updated_at: '2026-02-04T19:00:01.000000'
bees_version: '1.1'
---

Context: MCP entry points are the boundary where repo_root enters the system. They need to set context once via repo_root_context(), then all downstream calls read from it. This task establishes the clean boundary pattern.

What Needs to Change:
- Update ~15 entry points in mcp_ticket_ops.py, mcp_hive_ops.py, mcp_query_ops.py, mcp_index_ops.py
- Keep `repo_root: str | None = None` parameter as explicit fallback for non-Roots clients
- Create helper function `resolve_repo_root(ctx, explicit_root)` in mcp_repo_utils.py that tries Roots protocol first, then falls back to explicit_root
- Wrap each entry point's function body with `with repo_root_context(resolved_root):`
- Remove repo_root parameter from all downstream function calls within entry points
- Fix existing bug at mcp_ticket_ops.py:441 where _update_ticket uses repo_root before defining it

Why: Sets up clean architectural boundary - context set once at entry, read everywhere downstream. This eliminates the parameter threading problem.

Files: src/mcp_ticket_ops.py, src/mcp_hive_ops.py, src/mcp_query_ops.py, src/mcp_index_ops.py, src/mcp_repo_utils.py

Success Criteria:
- All entry points use repo_root_context() wrapper
- Optional repo_root param works for non-Roots clients
- resolve_repo_root() helper exists and handles both Roots and explicit param
- Bug at mcp_ticket_ops.py:441 is fixed
- No repo_root parameters passed to downstream calls
