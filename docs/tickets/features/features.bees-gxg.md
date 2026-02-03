---
id: features.bees-gxg
type: subtask
title: Remove all unreachable `if not resolved_repo_root:` checks
description: 'Remove the dead code checks at lines 1175-1179, 1455-1460, 1694-1697,
  1877-1880, 1973-1976, 2074-2077, 2332-2335, 2422-2425, 2525-2528, and 2909-2912
  in src/mcp_server.py.


  These checks are unreachable because get_repo_root() raises ValueError when it cannot
  determine repo_root (line 263), so resolved_repo_root can never be None/falsy.


  Implementation:

  - Remove the 10 `if not resolved_repo_root:` blocks and their associated error handling

  - Verify no other similar patterns exist in the file'
labels:
- refactor
- implementation
down_dependencies:
- features.bees-407
parent: features.bees-yp9
created_at: '2026-02-03T12:42:37.662916'
updated_at: '2026-02-03T12:48:16.456068'
status: completed
bees_version: '1.1'
---

Remove the dead code checks at lines 1175-1179, 1455-1460, 1694-1697, 1877-1880, 1973-1976, 2074-2077, 2332-2335, 2422-2425, 2525-2528, and 2909-2912 in src/mcp_server.py.

These checks are unreachable because get_repo_root() raises ValueError when it cannot determine repo_root (line 263), so resolved_repo_root can never be None/falsy.

Implementation:
- Remove the 10 `if not resolved_repo_root:` blocks and their associated error handling
- Verify no other similar patterns exist in the file
