---
id: features.bees-o0l
type: task
title: Fix failing test test_get_client_repo_root_raises_on_empty_roots
description: 'The test expects get_client_repo_root() to raise ValueError on empty
  roots, but the implementation now returns None instead (intentional behavior change
  from commit 715e452). Update test to expect None return value instead of ValueError.


  File: tests/test_mcp_roots.py:37'
labels:
- bug
up_dependencies:
- features.bees-lmo
down_dependencies:
- features.bees-yp9
- features.bees-lw7
- features.bees-v4d
parent: features.bees-h0a
children:
- features.bees-8u7
- features.bees-aqv
- features.bees-s3s
- features.bees-k40
- features.bees-mq4
created_at: '2026-02-03T12:35:28.777376'
updated_at: '2026-02-03T12:42:12.312260'
priority: 1
status: completed
bees_version: '1.1'
---

The test expects get_client_repo_root() to raise ValueError on empty roots, but the implementation now returns None instead (intentional behavior change from commit 715e452). Update test to expect None return value instead of ValueError.

File: tests/test_mcp_roots.py:37
