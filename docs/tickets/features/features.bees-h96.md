---
id: features.bees-h96
type: subtask
title: Decide on error handling strategy for get_repo_root
description: "**Context**: Function docstring at line 226 says \"Returns: Path if\
  \ repo root can be determined, None if roots protocol unavailable\" but implementation\
  \ at line 263 raises ValueError instead.\n\n**Requirements**: \n- Review how get_repo_root\
  \ is called throughout the codebase\n- Determine if callers expect None or ValueError\n\
  - Choose whether to:\n  - Option A: Change implementation to return None (update\
  \ line 263)\n  - Option B: Update docstring to document ValueError behavior (update\
  \ line 226)\n\n**Files Affected**:\n- src/mcp_server.py lines 220-270\n\n**Parent\
  \ Task**: features.bees-lw7\n\n**Decision: Option A - Change implementation to return\
  \ None**\n\n**Rationale**:\n1. All callers use `if resolved_repo_root:` pattern,\
  \ expecting None as valid return value\n2. Related task features.bees-o0l changed\
  \ get_client_repo_root() to return None instead of raising ValueError\n3. Docstring\
  \ already documents the correct behavior (return None)\n4. Returning None is more\
  \ Pythonic for \"optional value not available\" scenarios\n5. ValueError should\
  \ be reserved for truly invalid inputs (bad paths, non-absolute paths, etc.)\n\n\
  **Acceptance**: Decision documented as comment in this subtask explaining which\
  \ option was chosen and why."
down_dependencies:
- features.bees-rur
parent: features.bees-lw7
created_at: '2026-02-03T12:42:42.237339'
updated_at: '2026-02-03T12:52:01.487276'
status: completed
bees_version: '1.1'
---

**Context**: Function docstring at line 226 says "Returns: Path if repo root can be determined, None if roots protocol unavailable" but implementation at line 263 raises ValueError instead.

**Requirements**: 
- Review how get_repo_root is called throughout the codebase
- Determine if callers expect None or ValueError
- Choose whether to:
  - Option A: Change implementation to return None (update line 263)
  - Option B: Update docstring to document ValueError behavior (update line 226)

**Files Affected**:
- src/mcp_server.py lines 220-270

**Parent Task**: features.bees-lw7

**Decision: Option A - Change implementation to return None**

**Rationale**:
1. All callers use `if resolved_repo_root:` pattern, expecting None as valid return value
2. Related task features.bees-o0l changed get_client_repo_root() to return None instead of raising ValueError
3. Docstring already documents the correct behavior (return None)
4. Returning None is more Pythonic for "optional value not available" scenarios
5. ValueError should be reserved for truly invalid inputs (bad paths, non-absolute paths, etc.)

**Acceptance**: Decision documented as comment in this subtask explaining which option was chosen and why.
