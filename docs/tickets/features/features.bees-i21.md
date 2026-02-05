---
id: features.bees-i21
type: subtask
title: Add bees_repo fixture to conftest.py
description: 'Context: Base fixture for all test scenarios - creates minimal bees
  repository structure.


  Requirements:

  - Create `bees_repo` fixture in conftest.py

  - Use `@pytest.fixture(scope="function")` for test isolation

  - Create temporary directory with `.bees/` subdirectory

  - Yield the repo root Path object

  - Clean up temp directory after test


  Files: conftest.py


  Acceptance: Fixture creates temp dir with .bees/ structure and yields path'
down_dependencies:
- features.bees-5v6
- features.bees-5lj
- features.bees-q94
- features.bees-mtk
- features.bees-sp1
parent: features.bees-l71
created_at: '2026-02-05T08:09:23.025030'
updated_at: '2026-02-05T08:14:05.216530'
status: completed
bees_version: '1.1'
---

Context: Base fixture for all test scenarios - creates minimal bees repository structure.

Requirements:
- Create `bees_repo` fixture in conftest.py
- Use `@pytest.fixture(scope="function")` for test isolation
- Create temporary directory with `.bees/` subdirectory
- Yield the repo root Path object
- Clean up temp directory after test

Files: conftest.py

Acceptance: Fixture creates temp dir with .bees/ structure and yields path
