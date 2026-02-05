---
id: features.bees-abn
type: subtask
title: Refactor hive_utils.py to use get_repo_root()
description: |
  Context: Remove repo_root parameter from get_hive_config and load_hives_config and use context instead.

  What to Change:
  - Import get_repo_root from repo_context
  - For each function (get_hive_config, load_hives_config):
    1. Remove `repo_root: Path | None = None` parameter
    2. Add at start: `repo_root = get_repo_root()`
    3. Remove repo_root from any downstream calls

  Files: src/hive_utils.py

  Success Criteria:
  - No repo_root parameters in function signatures
  - Functions call get_repo_root() internally
  - Hive operations still work correctly
parent: features.bees-aa6
status: completed
created_at: '2026-02-04T19:15:22.000000'
updated_at: '2026-02-05T00:00:00.000000'
bees_version: '1.1'
---

Context: Remove repo_root parameter from get_hive_config and load_hives_config and use context instead.

What to Change:
- Import get_repo_root from repo_context
- For each function (get_hive_config, load_hives_config):
  1. Remove `repo_root: Path | None = None` parameter
  2. Add at start: `repo_root = get_repo_root()`
  3. Remove repo_root from any downstream calls

Files: src/hive_utils.py

Success Criteria:
- No repo_root parameters in function signatures
- Functions call get_repo_root() internally
- Hive operations still work correctly
