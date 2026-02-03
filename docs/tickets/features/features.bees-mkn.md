---
id: features.bees-mkn
type: subtask
title: Add unit tests for get_repo_root error handling
description: "**Context**: After implementing consistent error handling in get_repo_root,\
  \ ensure behavior is covered by unit tests.\n\n**Requirements**: \n- Test case:\
  \ roots protocol unavailable, no repo_root parameter → verify correct behavior (None\
  \ or ValueError based on implementation)\n- Test case: roots protocol unavailable,\
  \ valid repo_root parameter → verify returns Path\n- Test case: invalid repo_root\
  \ parameter → verify raises ValueError\n- Test edge cases: relative paths, non-existent\
  \ paths\n\n**Files Affected**:\n- tests/ (appropriate test file for mcp_server.py\
  \ functions)\n\n**Parent Task**: features.bees-lw7\n\n**Acceptance**: Test suite\
  \ covers all error paths and edge cases for get_repo_root function. All tests pass."
up_dependencies:
- features.bees-rur
down_dependencies:
- features.bees-is8
parent: features.bees-lw7
created_at: '2026-02-03T12:43:05.930442'
updated_at: '2026-02-03T12:54:44.402483'
status: completed
bees_version: '1.1'
---

**Context**: After implementing consistent error handling in get_repo_root, ensure behavior is covered by unit tests.

**Requirements**: 
- Test case: roots protocol unavailable, no repo_root parameter → verify correct behavior (None or ValueError based on implementation)
- Test case: roots protocol unavailable, valid repo_root parameter → verify returns Path
- Test case: invalid repo_root parameter → verify raises ValueError
- Test edge cases: relative paths, non-existent paths

**Files Affected**:
- tests/ (appropriate test file for mcp_server.py functions)

**Parent Task**: features.bees-lw7

**Acceptance**: Test suite covers all error paths and edge cases for get_repo_root function. All tests pass.
