---
id: features.bees-cmd
type: subtask
title: Update master_plan.md with repo_root fallback implementation
description: '**Context**: Document the architectural decision to support MCP clients
  without roots protocol via repo_root parameter fallback.


  **Requirements**:

  - Document the roots protocol dependency and why fallback is needed

  - Explain the fallback pattern: repo_root parameter -> roots protocol -> ValueError

  - List all 11 affected MCP tool functions

  - Document the error handling strategy when both methods fail

  - Explain integration with get_repo_root() helper function


  **Files**: docs/master_plan.md


  **Acceptance**: master_plan.md documents the repo_root fallback architecture and
  design decisions'
parent: features.bees-lmo
up_dependencies:
- features.bees-jsp
status: open
created_at: '2026-02-03T06:41:43.155319'
updated_at: '2026-02-03T06:41:43.155323'
bees_version: '1.1'
---

**Context**: Document the architectural decision to support MCP clients without roots protocol via repo_root parameter fallback.

**Requirements**:
- Document the roots protocol dependency and why fallback is needed
- Explain the fallback pattern: repo_root parameter -> roots protocol -> ValueError
- List all 11 affected MCP tool functions
- Document the error handling strategy when both methods fail
- Explain integration with get_repo_root() helper function

**Files**: docs/master_plan.md

**Acceptance**: master_plan.md documents the repo_root fallback architecture and design decisions
