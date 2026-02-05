---
id: features.bees-5lj
type: subtask
title: Add multi_hive fixture to conftest.py
description: 'Context: Builds on bees_repo fixture - adds multiple hives for cross-hive
  test scenarios.


  Requirements:

  - Create `multi_hive` fixture in conftest.py using `bees_repo` fixture

  - Use `@pytest.fixture(scope="function")`

  - Create ''backend'' and ''frontend'' hive directories with .hive/identity.json

  - Register both hives in .bees/config.json

  - Yield tuple of (repo_root, backend_path, frontend_path)


  Files: conftest.py

  Parent Task: features.bees-l71


  Acceptance: Fixture creates two hives with identity markers and config registrations'
up_dependencies:
- features.bees-i21
parent: features.bees-l71
created_at: '2026-02-05T08:09:33.499448'
updated_at: '2026-02-05T08:14:31.132999'
status: completed
bees_version: '1.1'
---

Context: Builds on bees_repo fixture - adds multiple hives for cross-hive test scenarios.

Requirements:
- Create `multi_hive` fixture in conftest.py using `bees_repo` fixture
- Use `@pytest.fixture(scope="function")`
- Create 'backend' and 'frontend' hive directories with .hive/identity.json
- Register both hives in .bees/config.json
- Yield tuple of (repo_root, backend_path, frontend_path)

Files: conftest.py
Parent Task: features.bees-l71

Acceptance: Fixture creates two hives with identity markers and config registrations
