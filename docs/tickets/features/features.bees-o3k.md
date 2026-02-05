---
id: features.bees-o3k
type: subtask
title: Run full test suite and fix all breakages from infrastructure changes
description: 'Context: After all test cleanup changes, need comprehensive validation
  that everything works.


  Requirements:

  - Run full pytest suite: `pytest tests/`

  - Investigate and fix any remaining test failures

  - Ensure 100% test pass rate

  - Document any unexpected issues found and how they were resolved


  Reference: Task features.bees-tv7

  Files: tests/


  Acceptance:

  - Full pytest run shows 0 failures

  - All tests pass with new centralized mocking infrastructure

  - No regressions introduced by cleanup changes'
parent: features.bees-tv7
up_dependencies:
- features.bees-8pf
- features.bees-wsn
- features.bees-90j
status: open
created_at: '2026-02-05T12:46:16.495465'
updated_at: '2026-02-05T12:46:16.495470'
bees_version: '1.1'
---

Context: After all test cleanup changes, need comprehensive validation that everything works.

Requirements:
- Run full pytest suite: `pytest tests/`
- Investigate and fix any remaining test failures
- Ensure 100% test pass rate
- Document any unexpected issues found and how they were resolved

Reference: Task features.bees-tv7
Files: tests/

Acceptance:
- Full pytest run shows 0 failures
- All tests pass with new centralized mocking infrastructure
- No regressions introduced by cleanup changes
