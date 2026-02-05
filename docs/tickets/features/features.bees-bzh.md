---
id: features.bees-bzh
type: subtask
title: Run unit tests and fix failures
description: 'Execute the full test suite after removing duplicate TestNormalizeHiveName
  class to verify:

  - No import errors in test_hive_utils.py

  - All remaining tests pass

  - No unexpected test failures


  Run: `poetry run pytest tests/test_hive_utils.py -v` and full suite `poetry run
  pytest -v`


  Fix any failures, even if pre-existing (must achieve 100% pass rate).


  Acceptance: All unit tests pass with 0 failures'
up_dependencies:
- features.bees-o1g
parent: features.bees-n1k
created_at: '2026-02-05T10:50:46.714171'
updated_at: '2026-02-05T10:51:57.401646'
status: completed
bees_version: '1.1'
---

Execute the full test suite after removing duplicate TestNormalizeHiveName class to verify:
- No import errors in test_hive_utils.py
- All remaining tests pass
- No unexpected test failures

Run: `poetry run pytest tests/test_hive_utils.py -v` and full suite `poetry run pytest -v`

Fix any failures, even if pre-existing (must achieve 100% pass rate).

Acceptance: All unit tests pass with 0 failures
