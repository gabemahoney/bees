---
id: features.bees-se5
type: task
title: Verify all 155 tests preserved and passing
description: 'Context: Final verification that the split preserved all tests without
  breaking anything.


  What Needs to Change:

  - Run `pytest tests/test_mcp_*.py` with verbose output

  - Count total tests executed across all three files

  - Verify count equals 155

  - Confirm all tests pass


  Why: Ensures the refactor achieved its goal without data loss or breaking changes.


  Success Criteria:

  - `pytest tests/test_mcp_*.py` shows 155 tests executed

  - All 155 tests pass

  - No single test file exceeds 1,600 lines


  Files: tests/test_mcp_*.py. Epic: features.bees-5y8'
up_dependencies:
- features.bees-xab
parent: features.bees-5y8
children:
- features.bees-5mb
- features.bees-fwb
- features.bees-jq8
- features.bees-tgl
created_at: '2026-02-05T16:12:56.460782'
updated_at: '2026-02-05T16:14:08.467605'
priority: 0
status: open
bees_version: '1.1'
---

Context: Final verification that the split preserved all tests without breaking anything.

What Needs to Change:
- Run `pytest tests/test_mcp_*.py` with verbose output
- Count total tests executed across all three files
- Verify count equals 155
- Confirm all tests pass

Why: Ensures the refactor achieved its goal without data loss or breaking changes.

Success Criteria:
- `pytest tests/test_mcp_*.py` shows 155 tests executed
- All 155 tests pass
- No single test file exceeds 1,600 lines

Files: tests/test_mcp_*.py. Epic: features.bees-5y8
