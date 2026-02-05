---
id: features.bees-aa6
type: task
title: Refactor remaining utility files
description: |
  Context: Several utility files have 1-2 functions each with repo_root parameter. Complete the refactor by removing all internal repo_root threading.

  What Needs to Change:
  - writer.py: Remove repo_root param from write_ticket_file
  - id_utils.py: Remove repo_root param from extract_existing_ids_from_all_hives
  - index_generator.py: Remove repo_root param from is_index_stale and generate_index
  - hive_utils.py: Remove repo_root param from get_hive_config and load_hives_config
  - watcher.py: Remove repo_root param from start_watcher
  - mcp_hive_utils.py: Remove repo_root param from validate_hive_path
  - For each function, replace with `repo_root = get_repo_root()` call internally

  Why: Complete the refactor - remove all internal repo_root threading. After this, only MCP entry points have repo_root parameters.

  Files: src/writer.py, src/id_utils.py, src/index_generator.py, src/hive_utils.py, src/watcher.py, src/mcp_hive_utils.py

  Note: See parent Epic features.bees-nho for detailed implementation patterns and code examples.

  Success Criteria:
  - No repo_root parameters in any internal utility functions
  - All functions use get_repo_root() internally
  - All modified functions still work correctly
  - File writing, ID extraction, indexing, hive ops, and watching all work
parent: features.bees-nho
children: ["features.bees-abk", "features.bees-abl", "features.bees-abm", "features.bees-abn", "features.bees-abo", "features.bees-abp", "features.bees-abq", "features.bees-abr"]
status: completed
priority: 0
up_dependencies: ["features.bees-aa2"]
created_at: '2026-02-04T19:00:05.000000'
updated_at: '2026-02-05T00:00:00.000000'
bees_version: '1.1'
---

Context: Several utility files have 1-2 functions each with repo_root parameter. Complete the refactor by removing all internal repo_root threading.

What Needs to Change:
- writer.py: Remove repo_root param from write_ticket_file
- id_utils.py: Remove repo_root param from extract_existing_ids_from_all_hives
- index_generator.py: Remove repo_root param from is_index_stale and generate_index
- hive_utils.py: Remove repo_root param from get_hive_config and load_hives_config
- watcher.py: Remove repo_root param from start_watcher
- mcp_hive_utils.py: Remove repo_root param from validate_hive_path
- For each function, replace with `repo_root = get_repo_root()` call internally

Why: Complete the refactor - remove all internal repo_root threading. After this, only MCP entry points have repo_root parameters.

Files: src/writer.py, src/id_utils.py, src/index_generator.py, src/hive_utils.py, src/watcher.py, src/mcp_hive_utils.py

Success Criteria:
- No repo_root parameters in any internal utility functions
- All functions use get_repo_root() internally
- All modified functions still work correctly
- File writing, ID extraction, indexing, hive ops, and watching all work
