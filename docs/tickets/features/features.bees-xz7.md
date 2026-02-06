---
id: features.bees-xz7
type: subtask
title: Verify file size and remaining test count
description: 'Context: After removing duplicated tests, verify the file meets the
  success criteria.


  What to Verify:

  - Check test_mcp_server.py line count (should be ~1,600 lines or less)

  - Count remaining test functions

  - Verify file only contains tool tests (no lifecycle or scan/validate)


  Files: tests/test_mcp_server.py


  Acceptance:

  - File is approximately 1,600 lines or less

  - Only tool tests remain in the file

  - File structure is clean and organized'
parent: features.bees-xab
up_dependencies:
- features.bees-g99
- features.bees-zkk
- features.bees-nj5
status: open
created_at: '2026-02-05T16:13:58.453843'
updated_at: '2026-02-05T16:13:58.453853'
bees_version: '1.1'
---

Context: After removing duplicated tests, verify the file meets the success criteria.

What to Verify:
- Check test_mcp_server.py line count (should be ~1,600 lines or less)
- Count remaining test functions
- Verify file only contains tool tests (no lifecycle or scan/validate)

Files: tests/test_mcp_server.py

Acceptance:
- File is approximately 1,600 lines or less
- Only tool tests remain in the file
- File structure is clean and organized
