---
id: features.bees-l4c
type: task
title: Review and potentially remove redundant conftest.py patch
description: '**Context**: tests/conftest.py:52-56 patches mcp_server functions that
  now just import from mcp_repo_utils. The comment suggests this may be redundant
  since patching mcp_repo_utils should be sufficient.


  **What to do**:

  - Analyze whether the mcp_server patch is still needed

  - If mcp_server just re-exports from mcp_repo_utils, remove the redundant patch

  - Run full test suite to verify tests still pass

  - Document the decision in conftest.py if patch is kept for a reason


  **Why**: Reduces maintenance burden and prevents confusion if import chain changes.


  **Files**: tests/conftest.py'
labels:
- bug
up_dependencies:
- features.bees-alr
parent: features.bees-d6o
children:
- features.bees-e6m
- features.bees-6iy
- features.bees-h95
- features.bees-4hp
- features.bees-41y
- features.bees-xaa
created_at: '2026-02-03T19:26:24.875656'
updated_at: '2026-02-03T19:32:27.807249'
priority: 1
status: completed
bees_version: '1.1'
---

**Context**: tests/conftest.py:52-56 patches mcp_server functions that now just import from mcp_repo_utils. The comment suggests this may be redundant since patching mcp_repo_utils should be sufficient.

**What to do**:
- Analyze whether the mcp_server patch is still needed
- If mcp_server just re-exports from mcp_repo_utils, remove the redundant patch
- Run full test suite to verify tests still pass
- Document the decision in conftest.py if patch is kept for a reason

**Why**: Reduces maintenance burden and prevents confusion if import chain changes.

**Files**: tests/conftest.py
