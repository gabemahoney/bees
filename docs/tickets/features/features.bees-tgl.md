---
id: features.bees-tgl
type: subtask
title: Verify no test file exceeds 1,600 lines
description: 'Context: Confirm the refactor achieved the goal of splitting the large
  file into manageable sizes.


  Requirements:

  - Use `wc -l tests/test_mcp_*.py` to count lines in each file

  - Verify each file is under 1,600 lines

  - Document the line counts for all three files

  - Confirm the split achieved its objective


  Files: tests/test_mcp_*.py


  Reference: Parent Task features.bees-se5


  Acceptance: All three test files are under 1,600 lines each, with documented line
  counts'
up_dependencies:
- features.bees-jq8
parent: features.bees-se5
created_at: '2026-02-05T16:14:08.464982'
updated_at: '2026-02-05T16:51:02.239334'
status: completed
bees_version: '1.1'
---

Context: Confirm the refactor achieved the goal of splitting the large file into manageable sizes.

Requirements:
- Use `wc -l tests/test_mcp_*.py` to count lines in each file
- Verify each file is under 1,600 lines
- Document the line counts for all three files
- Confirm the split achieved its objective

Files: tests/test_mcp_*.py

Reference: Parent Task features.bees-se5

Acceptance: All three test files are under 1,600 lines each, with documented line counts
