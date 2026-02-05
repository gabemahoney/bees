---
id: features.bees-ab8
type: subtask
title: Update mcp_index_ops.py entry points
description: |
  Context: Wrap all entry points in mcp_index_ops.py with repo_root_context and remove downstream repo_root params.

  What to Change:
  - Import repo_root_context from repo_context
  - Import resolve_repo_root from mcp_repo_utils
  - For each MCP tool function (_generate_index):
    1. Keep `repo_root: str | None = None` parameter
    2. Add at start: `resolved_root = await resolve_repo_root(ctx, repo_root)`
    3. Wrap function body: `with repo_root_context(resolved_root):`
    4. Remove repo_root from all downstream function calls

  Files: src/mcp_index_ops.py

  Success Criteria:
  - All entry points use context pattern
  - No repo_root passed to downstream calls
  - Code still functional
parent: features.bees-aa2
status: completed
created_at: '2026-02-04T19:15:07.000000'
updated_at: '2026-02-04T19:15:07.000000'
bees_version: '1.1'
---

Context: Wrap all entry points in mcp_index_ops.py with repo_root_context and remove downstream repo_root params.

What to Change:
- Import repo_root_context from repo_context
- Import resolve_repo_root from mcp_repo_utils
- For each MCP tool function (_generate_index):
  1. Keep `repo_root: str | None = None` parameter
  2. Add at start: `resolved_root = await resolve_repo_root(ctx, repo_root)`
  3. Wrap function body: `with repo_root_context(resolved_root):`
  4. Remove repo_root from all downstream function calls

Files: src/mcp_index_ops.py

Success Criteria:
- All entry points use context pattern
- No repo_root passed to downstream calls
- Code still functional
