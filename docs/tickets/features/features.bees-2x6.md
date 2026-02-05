---
id: features.bees-2x6
type: subtask
title: Remove duplicate normalize_hive_name tests from test_config.py
description: '**Context**: test_config.py contains duplicate normalize_hive_name tests
  that overlap with test_hive_utils.py. Keep canonical version in test_hive_utils.py
  since normalize_hive_name is from id_utils module.


  **Work to do**:

  - Delete TestNormalizeHiveName class from test_config.py (lines 908-963)

  - Verify remaining tests in test_config.py still pass after deletion

  - Ensure test_hive_utils.py has adequate coverage for normalize_hive_name


  **Files**: tests/test_config.py


  **Acceptance**: TestNormalizeHiveName removed from test_config.py, all tests pass'
parent: features.bees-lnx
created_at: '2026-02-05T10:20:13.715241'
updated_at: '2026-02-05T10:47:15.743672'
status: completed
bees_version: '1.1'
---

**Context**: test_config.py contains duplicate normalize_hive_name tests that overlap with test_hive_utils.py. Keep canonical version in test_hive_utils.py since normalize_hive_name is from id_utils module.

**Work to do**:
- Delete TestNormalizeHiveName class from test_config.py (lines 908-963)
- Verify remaining tests in test_config.py still pass after deletion
- Ensure test_hive_utils.py has adequate coverage for normalize_hive_name

**Files**: tests/test_config.py

**Acceptance**: TestNormalizeHiveName removed from test_config.py, all tests pass
