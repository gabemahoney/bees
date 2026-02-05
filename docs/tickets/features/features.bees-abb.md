---
id: features.bees-abb
type: subtask
title: Refactor config.py functions to use get_repo_root()
description: |
  Context: Remove repo_root parameter from all 10 config.py functions and use context instead.

  What to Change:
  - Import get_repo_root from repo_context
  - For each function (get_config_path, ensure_bees_dir, load_bees_config, save_bees_config, init_bees_config_if_needed, validate_unique_hive_name, load_hive_config_dict, write_hive_config_dict, register_hive_dict, plus one more):
    1. Remove `repo_root: Path | None = None` parameter
    2. Add at start: `repo_root = get_repo_root()`
    3. Remove repo_root from calls to other config functions
  - Update any internal function calls within config.py to not pass repo_root

  Files: src/config.py

  Success Criteria:
  - No repo_root parameters in function signatures
  - All functions call get_repo_root() internally
  - No repo_root passed between config functions
  - Functions still work correctly
parent: features.bees-aa3
status: completed
created_at: '2026-02-04T19:15:10.000000'
updated_at: '2026-02-04T19:15:10.000000'
bees_version: '1.1'
---

Context: Remove repo_root parameter from all 10 config.py functions and use context instead.

What to Change:
- Import get_repo_root from repo_context
- For each function (get_config_path, ensure_bees_dir, load_bees_config, save_bees_config, init_bees_config_if_needed, validate_unique_hive_name, load_hive_config_dict, write_hive_config_dict, register_hive_dict, plus one more):
  1. Remove `repo_root: Path | None = None` parameter
  2. Add at start: `repo_root = get_repo_root()`
  3. Remove repo_root from calls to other config functions
- Update any internal function calls within config.py to not pass repo_root

Files: src/config.py

Success Criteria:
- No repo_root parameters in function signatures
- All functions call get_repo_root() internally
- No repo_root passed between config functions
- Functions still work correctly
