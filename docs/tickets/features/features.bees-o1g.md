---
id: features.bees-o1g
type: subtask
title: Remove TestNormalizeHiveName class from test_hive_utils.py
description: 'Remove the duplicate TestNormalizeHiveName class from test_hive_utils.py
  (lines 13-71).


  Context: The canonical version exists in test_id_utils.py with more comprehensive
  coverage (4 test methods covering all edge cases). This duplicate creates maintenance
  overhead.


  Files to modify:

  - tests/test_hive_utils.py: Delete lines 13-71 (entire TestNormalizeHiveName class)


  Acceptance: TestNormalizeHiveName class no longer exists in test_hive_utils.py'
down_dependencies:
- features.bees-bzh
parent: features.bees-n1k
created_at: '2026-02-05T10:50:40.563467'
updated_at: '2026-02-05T10:51:25.162304'
status: completed
bees_version: '1.1'
---

Remove the duplicate TestNormalizeHiveName class from test_hive_utils.py (lines 13-71).

Context: The canonical version exists in test_id_utils.py with more comprehensive coverage (4 test methods covering all edge cases). This duplicate creates maintenance overhead.

Files to modify:
- tests/test_hive_utils.py: Delete lines 13-71 (entire TestNormalizeHiveName class)

Acceptance: TestNormalizeHiveName class no longer exists in test_hive_utils.py
