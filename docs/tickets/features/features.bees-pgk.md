---
id: features.bees-pgk
type: task
title: Update CLAUDE.md to reflect new contextvars architecture
description: |
  Update CLAUDE.md documentation to describe the new contextvars-based architecture instead of the old threading problem.
  
  **Current state:**
  CLAUDE.md still describes the old problem of manually threading repo_root through 24+ functions.
  
  **What to update:**
  The section about "MCP Roots Protocol and repo_root" should be updated to reflect:
  
  1. **New architecture:**
     - MCP entry points call resolve_repo_root(ctx, repo_root)
     - Entry points wrap logic with repo_root_context(resolved_root)
     - Downstream functions call get_repo_root() from contextvars
     - No manual parameter threading required
  
  2. **How it works:**
     - Entry points set context once
     - Context is async-safe (contextvars)
     - Request-scoped isolation
     - Explicit repo_root parameter for non-Roots clients
  
  3. **Error handling:**
     - Clear RuntimeError when context not set
     - McpError and NotFoundError caught for non-Roots clients
     - Graceful fallback to explicit parameter
  
  **Files:**
  - CLAUDE.md (MCP Roots Protocol section)
  
  **Success criteria:**
  - Documentation accurately describes new contextvars architecture
  - Old threading problem description removed or updated
  - Examples show current patterns (repo_root_context, get_repo_root())
  - Clear for future developers to understand
parent: features.bees-nho
status: closed
priority: 2
labels: ["docs"]
created_at: '2026-02-05T07:03:00.000000'
updated_at: '2026-02-05T15:05:11.000000'
bees_version: '1.1'
---

Update documentation to reflect contextvars architecture instead of old threading approach.
