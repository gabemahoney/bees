---
id: features.bees-abp
type: subtask
title: Refactor mcp_hive_utils.py to use get_repo_root()
description: |
  Context: Remove repo_root parameter from validate_hive_path and use context instead.

  What to Change:
  - Import get_repo_root from repo_context
  - In validate_hive_path function:
    1. Remove `repo_root: Path | None = None` parameter
    2. Add at start: `repo_root = get_repo_root()`
    3. Remove repo_root from any downstream calls

  Files: src/mcp_hive_utils.py

  Success Criteria:
  - No repo_root parameter in function signature
  - Function calls get_repo_root() internally
  - Hive path validation still works correctly
parent: features.bees-aa6
status: completed
created_at: '2026-02-04T19:15:24.000000'
updated_at: '2026-02-05T00:00:00.000000'
bees_version: '1.1'
---

Context: Remove repo_root parameter from validate_hive_path and use context instead.

What to Change:
- Import get_repo_root from repo_context
- In validate_hive_path function:
  1. Remove `repo_root: Path | None = None` parameter
  2. Add at start: `repo_root = get_repo_root()`
  3. Remove repo_root from any downstream calls

Files: src/mcp_hive_utils.py

Success Criteria:
- No repo_root parameter in function signature
- Function calls get_repo_root() internally
- Hive path validation still works correctly
