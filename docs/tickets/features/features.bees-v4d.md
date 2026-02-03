---
id: features.bees-v4d
type: task
title: Add missing test coverage for repo_root parameter
description: 'New repo_root parameter was added to _update_ticket, _delete_ticket,
  _execute_query, _execute_freeform_query, _show_ticket, _abandon_hive, _rename_hive,
  and _sanitize_hive but only _create_ticket, _list_hives, and _colonize_hive have
  explicit tests for the repo_root parameter.


  File: tests/test_mcp_roots.py'
labels:
- testing
up_dependencies:
- features.bees-o0l
parent: features.bees-h0a
children:
- features.bees-4mj
- features.bees-g3z
- features.bees-vfj
- features.bees-omb
- features.bees-lva
- features.bees-if9
- features.bees-g2e
- features.bees-d1y
- features.bees-y5t
- features.bees-k4v
- features.bees-qio
- features.bees-49h
created_at: '2026-02-03T12:42:12.305738'
updated_at: '2026-02-03T13:03:22.058650'
priority: 1
status: completed
bees_version: '1.1'
---

New repo_root parameter was added to _update_ticket, _delete_ticket, _execute_query, _execute_freeform_query, _show_ticket, _abandon_hive, _rename_hive, and _sanitize_hive but only _create_ticket, _list_hives, and _colonize_hive have explicit tests for the repo_root parameter.

File: tests/test_mcp_roots.py
