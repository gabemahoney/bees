---
id: features.bees-l71
type: task
title: Create pytest fixtures in conftest.py
description: 'Context: Tests currently duplicate fixture setup code. Need reusable
  tiered fixtures for different test scenarios.


  What Needs to Change:

  - Add `bees_repo` fixture to conftest.py - creates bare repo with .bees directory

  - Add `single_hive` fixture - builds on bees_repo, adds single ''backend'' hive
  with config

  - Add `multi_hive` fixture - builds on bees_repo, adds backend + frontend hives

  - Add `hive_with_tickets` fixture - builds on single_hive, adds pre-created epic/task/subtask


  Files: conftest.py

  Epic: features.bees-y6w


  Why: Tiered fixtures allow tests to use appropriate setup level without duplicate
  code.


  Success Criteria:

  - All 4 fixtures available in conftest.py

  - Fixtures properly use pytest scope and composition

  - Each fixture creates expected directory structure'
down_dependencies:
- features.bees-m6i
- features.bees-u71
- features.bees-jc0
parent: features.bees-y6w
children:
- features.bees-i21
- features.bees-5v6
- features.bees-5lj
- features.bees-di9
- features.bees-q94
- features.bees-mtk
- features.bees-sp1
- features.bees-pj5
created_at: '2026-02-05T08:08:23.950282'
updated_at: '2026-02-05T08:18:38.854958'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Tests currently duplicate fixture setup code. Need reusable tiered fixtures for different test scenarios.

What Needs to Change:
- Add `bees_repo` fixture to conftest.py - creates bare repo with .bees directory
- Add `single_hive` fixture - builds on bees_repo, adds single 'backend' hive with config
- Add `multi_hive` fixture - builds on bees_repo, adds backend + frontend hives
- Add `hive_with_tickets` fixture - builds on single_hive, adds pre-created epic/task/subtask

Files: conftest.py
Epic: features.bees-y6w

Why: Tiered fixtures allow tests to use appropriate setup level without duplicate code.

Success Criteria:
- All 4 fixtures available in conftest.py
- Fixtures properly use pytest scope and composition
- Each fixture creates expected directory structure
