---
id: features.bees-hyq
type: subtask
title: Identify all duplicate test scenarios
description: '**Context**: Task features.bees-lnx requires identifying and removing
  duplicate tests across test_config.py and test_hive_utils.py.


  **Work to do**:

  - Compare test methods in test_config.py:TestNormalizeHiveName (lines 908-963)

  - Compare test methods in test_hive_utils.py:TestNormalizeHiveName (lines 13-34)

  - Document which tests are exact duplicates vs unique scenarios

  - Create a mapping showing which tests to keep and which to delete


  **Files**: tests/test_config.py, tests/test_hive_utils.py


  **Acceptance**: Documented list of duplicate tests with keep/delete decisions'
parent: features.bees-lnx
created_at: '2026-02-05T10:20:10.050021'
updated_at: '2026-02-05T10:46:40.701077'
status: completed
bees_version: '1.1'
---

**Context**: Task features.bees-lnx requires identifying and removing duplicate tests across test_config.py and test_hive_utils.py.

**Work to do**:
- Compare test methods in test_config.py:TestNormalizeHiveName (lines 908-963)
- Compare test methods in test_hive_utils.py:TestNormalizeHiveName (lines 13-34)
- Document which tests are exact duplicates vs unique scenarios
- Create a mapping showing which tests to keep and which to delete

**Files**: tests/test_config.py, tests/test_hive_utils.py

**Acceptance**: Documented list of duplicate tests with keep/delete decisions
