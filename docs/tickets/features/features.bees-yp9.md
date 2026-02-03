---
id: features.bees-yp9
type: task
title: Remove dead code checks for resolved_repo_root in MCP tools
description: 'Lines 1175-1179, 1455-1460, 1694-1697, and 8+ other locations check
  `if not resolved_repo_root:` but this is unreachable code since get_repo_root()
  raises ValueError when it cannot determine repo_root (see line 263). Remove these
  dead checks or update get_repo_root() to return None.


  File: src/mcp_server.py'
labels:
- refactor
up_dependencies:
- features.bees-o0l
parent: features.bees-h0a
children:
- features.bees-gxg
- features.bees-f2n
- features.bees-407
- features.bees-csv
created_at: '2026-02-03T12:42:08.307521'
updated_at: '2026-02-03T12:42:48.241760'
priority: 1
status: completed
bees_version: '1.1'
---

Lines 1175-1179, 1455-1460, 1694-1697, and 8+ other locations check `if not resolved_repo_root:` but this is unreachable code since get_repo_root() raises ValueError when it cannot determine repo_root (see line 263). Remove these dead checks or update get_repo_root() to return None.

File: src/mcp_server.py
