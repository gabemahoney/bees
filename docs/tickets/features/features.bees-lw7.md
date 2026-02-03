---
id: features.bees-lw7
type: task
title: Fix inconsistent None handling in get_repo_root
description: 'Function docstring says "Returns: Path if repo root can be determined,
  None if roots protocol unavailable" but implementation at line 263 raises ValueError
  instead of returning None. Either update docstring to match implementation or change
  implementation to return None.


  File: src/mcp_server.py:263'
labels:
- bug
up_dependencies:
- features.bees-o0l
parent: features.bees-h0a
children:
- features.bees-h96
- features.bees-rur
- features.bees-o4d
- features.bees-oud
- features.bees-mkn
- features.bees-is8
created_at: '2026-02-03T12:42:10.210556'
updated_at: '2026-02-03T12:58:50.624958'
priority: 1
status: completed
bees_version: '1.1'
---

Function docstring says "Returns: Path if repo root can be determined, None if roots protocol unavailable" but implementation at line 263 raises ValueError instead of returning None. Either update docstring to match implementation or change implementation to return None.

File: src/mcp_server.py:263
