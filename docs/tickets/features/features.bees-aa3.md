---
id: features.bees-aa3
type: task
title: Refactor config.py functions
description: |
  Context: config.py has 10 functions passing repo_root parameter - the most affected file. Removing parameter threading here provides the largest simplification.

  What Needs to Change:
  - Remove `repo_root: Path | None = None` parameter from all 10 functions:
    - get_config_path
    - ensure_bees_dir
    - load_bees_config
    - save_bees_config
    - init_bees_config_if_needed
    - validate_unique_hive_name
    - load_hive_config_dict
    - write_hive_config_dict
    - register_hive_dict
    - And one more (check file for complete list)
  - Replace with `repo_root = get_repo_root()` call at start of each function
  - Remove all repo_root parameter passing between functions (e.g., load_bees_config calling get_config_path)

  Why: Largest source of parameter threading - 10 functions affected. Simplifying this file provides immediate readability benefit.

  Files: src/config.py

  Note: See parent Epic features.bees-nho for detailed implementation patterns and code examples.

  Success Criteria:
  - No repo_root parameters in any config.py function signatures
  - All functions call get_repo_root() internally
  - Functions still work correctly with context set by entry points
  - No calls between config functions pass repo_root
parent: features.bees-nho
children: ["features.bees-abb", "features.bees-abc", "features.bees-abd"]
status: completed
priority: 0
up_dependencies: ["features.bees-aa2"]
created_at: '2026-02-04T19:00:02.000000'
updated_at: '2026-02-04T19:00:02.000000'
bees_version: '1.1'
---

Context: config.py has 10 functions passing repo_root parameter - the most affected file. Removing parameter threading here provides the largest simplification.

What Needs to Change:
- Remove `repo_root: Path | None = None` parameter from all 10 functions:
  - get_config_path
  - ensure_bees_dir
  - load_bees_config
  - save_bees_config
  - init_bees_config_if_needed
  - validate_unique_hive_name
  - load_hive_config_dict
  - write_hive_config_dict
  - register_hive_dict
  - And one more (check file for complete list)
- Replace with `repo_root = get_repo_root()` call at start of each function
- Remove all repo_root parameter passing between functions (e.g., load_bees_config calling get_config_path)

Why: Largest source of parameter threading - 10 functions affected. Simplifying this file provides immediate readability benefit.

Files: src/config.py

Success Criteria:
- No repo_root parameters in any config.py function signatures
- All functions call get_repo_root() internally
- Functions still work correctly with context set by entry points
- No calls between config functions pass repo_root
