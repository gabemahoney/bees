---
id: features.bees-4ju
type: task
title: Fix failing context tests in test_mcp_roots.py
description: 'Tests test_list_hives_uses_context, test_create_ticket_uses_context,
  test_colonize_hive_uses_context are passing Mock objects where string paths are
  expected for repo_root parameter. Update tests to use repo_root=str(test_repo) instead
  of letting Mock objects propagate.


  File: tests/test_mcp_roots.py'
labels:
- bug
up_dependencies:
- features.bees-lmo
parent: features.bees-h0a
children:
- features.bees-jtc
- features.bees-kuo
- features.bees-0mb
- features.bees-3sy
created_at: '2026-02-03T12:35:28.823846'
updated_at: '2026-02-03T12:45:32.304164'
priority: 1
status: completed
bees_version: '1.1'
---

Tests test_list_hives_uses_context, test_create_ticket_uses_context, test_colonize_hive_uses_context are passing Mock objects where string paths are expected for repo_root parameter. Update tests to use repo_root=str(test_repo) instead of letting Mock objects propagate.

File: tests/test_mcp_roots.py
