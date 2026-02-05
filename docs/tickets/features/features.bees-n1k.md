---
id: features.bees-n1k
type: task
title: Remove duplicate TestNormalizeHiveName from test_hive_utils.py
description: Remove the TestNormalizeHiveName class from test_hive_utils.py (lines
  13-71). The canonical consolidated version with 4 comprehensive tests exists in
  test_id_utils.py (created in features.bees-4tm). Having both creates duplication
  and maintenance overhead.
labels:
- code-review-fix
up_dependencies:
- features.bees-lnx
down_dependencies:
- features.bees-r13
parent: features.bees-utd
children:
- features.bees-o1g
- features.bees-bzh
created_at: '2026-02-05T10:50:14.150876'
updated_at: '2026-02-05T10:54:16.033733'
priority: 1
status: completed
bees_version: '1.1'
---

Remove the TestNormalizeHiveName class from test_hive_utils.py (lines 13-71). The canonical consolidated version with 4 comprehensive tests exists in test_id_utils.py (created in features.bees-4tm). Having both creates duplication and maintenance overhead.
