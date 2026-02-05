---
id: features.bees-xo8
type: task
title: Migrate MCP Hive Management Tests
description: 'Migrate test_mcp_create_ticket_hive.py, test_create_ticket_hive_validation.py,
  test_mcp_server.py, and test_mcp_rename_hive.py to use conftest.py fixtures. Remove
  all local setup_* fixture functions. Update test signatures to use shared bees_repo,
  single_hive, and multi_hive fixtures. Verify MCP operations still work correctly.
  Files: tests/test_mcp_create_ticket_hive.py, tests/test_create_ticket_hive_validation.py,
  tests/test_mcp_server.py, tests/test_mcp_rename_hive.py. Epic: features.bees-74p'
parent: features.bees-74p
children:
- features.bees-hv7
- features.bees-4jr
- features.bees-vj6
- features.bees-yus
- features.bees-v4c
created_at: '2026-02-05T12:05:02.745429'
updated_at: '2026-02-05T12:30:31.047218'
priority: 0
status: completed
bees_version: '1.1'
---

Migrate test_mcp_create_ticket_hive.py, test_create_ticket_hive_validation.py, test_mcp_server.py, and test_mcp_rename_hive.py to use conftest.py fixtures. Remove all local setup_* fixture functions. Update test signatures to use shared bees_repo, single_hive, and multi_hive fixtures. Verify MCP operations still work correctly. Files: tests/test_mcp_create_ticket_hive.py, tests/test_create_ticket_hive_validation.py, tests/test_mcp_server.py, tests/test_mcp_rename_hive.py. Epic: features.bees-74p
