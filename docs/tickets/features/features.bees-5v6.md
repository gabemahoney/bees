---
id: features.bees-5v6
type: subtask
title: Add single_hive fixture to conftest.py
description: 'Context: Builds on bees_repo fixture - adds single configured hive for
  simple test scenarios.


  Requirements:

  - Create `single_hive` fixture in conftest.py using `bees_repo` fixture

  - Use `@pytest.fixture(scope="function")`

  - Create ''backend'' hive directory structure (with .hive/identity.json)

  - Register hive in .bees/config.json with proper normalized name

  - Yield tuple of (repo_root, hive_path)


  Files: conftest.py

  Parent Task: features.bees-l71


  Acceptance: Fixture creates backend hive with identity marker and config registration'
up_dependencies:
- features.bees-i21
down_dependencies:
- features.bees-di9
parent: features.bees-l71
created_at: '2026-02-05T08:09:28.863956'
updated_at: '2026-02-05T08:14:19.763406'
status: completed
bees_version: '1.1'
---

Context: Builds on bees_repo fixture - adds single configured hive for simple test scenarios.

Requirements:
- Create `single_hive` fixture in conftest.py using `bees_repo` fixture
- Use `@pytest.fixture(scope="function")`
- Create 'backend' hive directory structure (with .hive/identity.json)
- Register hive in .bees/config.json with proper normalized name
- Yield tuple of (repo_root, hive_path)

Files: conftest.py
Parent Task: features.bees-l71

Acceptance: Fixture creates backend hive with identity marker and config registration
