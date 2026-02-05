---
id: features.bees-pgj
type: task
title: Refactor colonize_hive_core for consistent context pattern
description: |
  Review and potentially refactor colonize_hive_core() in mcp_hive_ops.py to use the standard context pattern.
  
  **Current pattern (inconsistent):**
  ```python
  # Line 95-97: Gets repo_root directly
  repo_root = await get_repo_root(ctx)
  if repo_root:
      # Line 131: THEN sets context later
      with repo_root_context(repo_root):
          # logic here
  ```
  
  **Standard pattern used by other entry points:**
  ```python
  resolved_root = await resolve_repo_root(ctx, repo_root)
  with repo_root_context(resolved_root):
      # all logic here
  ```
  
  **Complexity:**
  The function has branching logic between lines 95-131 before the context is set.
  This makes it harder to reason about and inconsistent with other entry points.
  
  **Action:**
  1. Review colonize_hive_core() (lines 92-131 in mcp_hive_ops.py)
  2. Determine if refactoring to standard pattern is safe
  3. If safe, refactor to use resolve_repo_root() + immediate context setup
  4. If not safe, document why this function needs different pattern
  
  **Success criteria:**
  - Function either uses standard pattern OR has documented reason for difference
  - All tests still pass
  - Function behavior unchanged
parent: features.bees-nho
status: closed
priority: 2
labels: ["refactor", "consistency"]
created_at: '2026-02-05T07:02:00.000000'
updated_at: '2026-02-05T15:06:39.000000'
bees_version: '1.1'
---

Review colonize_hive_core for consistency with standard context pattern.
