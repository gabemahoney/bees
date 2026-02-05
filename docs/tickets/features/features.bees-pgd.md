---
id: features.bees-pgd
type: task
title: Fix test suite for utility file refactor
description: |
  Fix test files that haven't been updated for the refactored utility file signatures from features.bees-aa6:
  
  1. Fix test_mcp_hive_utils.py - remove repo_root parameter from validate_hive_path() calls
  2. Fix test_mcp_index_ops.py - add await to _generate_index() calls (now async)
  3. Fix test_colonize_hive.py - update validate_hive_path() mock signatures
  4. Fix test_mcp_hive_inference.py - add await to async ticket operations
  5. Fix test_mcp_roots.py - add await to async MCP function calls
  6. Fix test_mcp_server.py - update validate_hive_path() calls and add await
  7. Fix test_query_tools.py - add await to async query function calls
  8. Fix test_ticket_factory_hive.py - update create_* calls for context
  9. Register pytest mark 'no_repo_context' in pyproject.toml
parent: features.bees-nho
up_dependencies: ["features.bees-aa6"]
status: completed
priority: 1
labels: ["bug", "code-review", "tests"]
created_at: '2026-02-04T22:00:00.000000'
updated_at: '2026-02-05T14:30:00.000000'
bees_version: '1.1'
---

Fix all test files to match refactored function signatures.
