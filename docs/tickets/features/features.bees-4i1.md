---
id: features.bees-4i1
type: task
title: Analyze test_mcp_server.py structure and categorize tests
description: 'Context: Before splitting the 3,159-line file, we need to identify which
  tests belong in each new file category (lifecycle, scan/validate, remaining).


  What Needs to Change:

  - Read tests/test_mcp_server.py and identify all test functions

  - Categorize each test as: lifecycle (startup/shutdown/tool registration), scan_validate
  (scan and validation logic), or remaining (tool tests)

  - Create categorization document listing test names by category

  - Verify total count matches 155 tests


  Why: Ensures we split tests correctly and don''t lose any during migration.


  Success Criteria:

  - Categorization document exists showing all 155 tests grouped by target file

  - Each category matches expected line counts (~400 for lifecycle, ~300 for scan_validate,
  ~1,600 remaining)


  Files: tests/test_mcp_server.py. Epic: features.bees-5y8'
down_dependencies:
- features.bees-xhi
- features.bees-82b
parent: features.bees-5y8
children:
- features.bees-ysm
- features.bees-krd
- features.bees-4e2
- features.bees-6xw
- features.bees-p2j
- features.bees-o5f
- features.bees-kgk
- features.bees-a9n
- features.bees-99t
- features.bees-58n
created_at: '2026-02-05T16:12:45.878843'
updated_at: '2026-02-05T16:22:49.823271'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Before splitting the 3,159-line file, we need to identify which tests belong in each new file category (lifecycle, scan/validate, remaining).

What Needs to Change:
- Read tests/test_mcp_server.py and identify all test functions
- Categorize each test as: lifecycle (startup/shutdown/tool registration), scan_validate (scan and validation logic), or remaining (tool tests)
- Create categorization document listing test names by category
- Verify total count matches 155 tests

Why: Ensures we split tests correctly and don't lose any during migration.

Success Criteria:
- Categorization document exists showing all 155 tests grouped by target file
- Each category matches expected line counts (~400 for lifecycle, ~300 for scan_validate, ~1,600 remaining)

Files: tests/test_mcp_server.py. Epic: features.bees-5y8
