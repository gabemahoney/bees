---
id: features.bees-o5f
type: subtask
title: Verify categorization totals and line counts
description: 'Context: Must ensure categorization is accurate before proceeding with
  file split.


  What to Verify:

  - Total test count across all categories = 155 (no duplicates, no missing tests)

  - Lifecycle category line estimate ~400 lines

  - Scan/validate category line estimate ~300 lines

  - Remaining category line estimate ~1,600 lines

  - Total lines across categories ~3,159 (matches current file)

  - Each test appears in exactly one category

  - No overlap between categories


  Verification Methods:

  - Count tests per category, sum to 155

  - Calculate line ranges for each category based on first/last test line numbers

  - Check for duplicate test names across categories

  - Compare against original file line count (3,178 total)


  Why: Prevents errors during file split; ensures clean migration with no lost tests.


  Acceptance Criteria:

  - Verification report shows all checks pass

  - Test count = 155

  - Line estimates within 10% of targets

  - No duplicates or missing tests found

  - Categorization document updated with verification stamp


  Reference: Task features.bees-4i1

  Files: tests/test_mcp_server.py

  Depends on: features.bees-p2j'
up_dependencies:
- features.bees-p2j
parent: features.bees-4i1
created_at: '2026-02-05T16:14:33.550952'
updated_at: '2026-02-05T16:22:20.130810'
status: completed
bees_version: '1.1'
---

Context: Must ensure categorization is accurate before proceeding with file split.

What to Verify:
- Total test count across all categories = 155 (no duplicates, no missing tests)
- Lifecycle category line estimate ~400 lines
- Scan/validate category line estimate ~300 lines
- Remaining category line estimate ~1,600 lines
- Total lines across categories ~3,159 (matches current file)
- Each test appears in exactly one category
- No overlap between categories

Verification Methods:
- Count tests per category, sum to 155
- Calculate line ranges for each category based on first/last test line numbers
- Check for duplicate test names across categories
- Compare against original file line count (3,178 total)

Why: Prevents errors during file split; ensures clean migration with no lost tests.

Acceptance Criteria:
- Verification report shows all checks pass
- Test count = 155
- Line estimates within 10% of targets
- No duplicates or missing tests found
- Categorization document updated with verification stamp

Reference: Task features.bees-4i1
Files: tests/test_mcp_server.py
Depends on: features.bees-p2j
