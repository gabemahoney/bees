---
id: features.bees-nj5
type: subtask
title: Clean up orphaned imports and helper functions
description: "Context: After removing lifecycle and scan/validate tests, some imports\
  \ and helper functions may no longer be needed.\n\nWhat to Clean:\n- Review all\
  \ imports in test_mcp_server.py\n- Remove any imports not used by remaining tests\n\
  - Check for helper functions/fixtures only used by removed tests\n- Remove orphaned\
  \ helper functions\n\nFiles: tests/test_mcp_server.py\n\nAcceptance: \n- No unused\
  \ imports remain\n- No orphaned helper functions remain\n- File passes linting checks"
down_dependencies:
- features.bees-xz7
- features.bees-11n
parent: features.bees-xab
created_at: '2026-02-05T16:13:51.415819'
updated_at: '2026-02-05T16:45:49.419555'
status: completed
bees_version: '1.1'
---

Context: After removing lifecycle and scan/validate tests, some imports and helper functions may no longer be needed.

What to Clean:
- Review all imports in test_mcp_server.py
- Remove any imports not used by remaining tests
- Check for helper functions/fixtures only used by removed tests
- Remove orphaned helper functions

Files: tests/test_mcp_server.py

Acceptance: 
- No unused imports remain
- No orphaned helper functions remain
- File passes linting checks
