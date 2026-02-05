---
id: features.bees-nzq
type: subtask
title: Run unit tests and fix failures
description: '**Context**: After reducing normalize_hive_name test coverage in features.bees-2u5,
  validate all tests pass and coverage is maintained.


  **Requirements**:

  - Execute full test suite: `pytest tests/test_id_utils.py -v`

  - Verify exactly 4 normalize_hive_name tests exist and all pass

  - Run coverage check: `pytest --cov=src.id_utils --cov-report=term-missing`

  - Confirm normalize_hive_name() coverage unchanged from baseline

  - Fix any test failures (even if you believe they are pre-existing)


  **Acceptance**:

  - `pytest tests/test_id_utils.py` exits 0 (100% pass rate)

  - TestNormalizeHiveName has exactly 4 test methods

  - Coverage report shows no regression for src/id_utils.py'
up_dependencies:
- features.bees-2u5
parent: features.bees-4tm
created_at: '2026-02-05T10:20:12.145766'
updated_at: '2026-02-05T10:24:03.580117'
status: completed
bees_version: '1.1'
---

**Context**: After reducing normalize_hive_name test coverage in features.bees-2u5, validate all tests pass and coverage is maintained.

**Requirements**:
- Execute full test suite: `pytest tests/test_id_utils.py -v`
- Verify exactly 4 normalize_hive_name tests exist and all pass
- Run coverage check: `pytest --cov=src.id_utils --cov-report=term-missing`
- Confirm normalize_hive_name() coverage unchanged from baseline
- Fix any test failures (even if you believe they are pre-existing)

**Acceptance**:
- `pytest tests/test_id_utils.py` exits 0 (100% pass rate)
- TestNormalizeHiveName has exactly 4 test methods
- Coverage report shows no regression for src/id_utils.py
