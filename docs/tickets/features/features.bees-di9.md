---
id: features.bees-di9
type: subtask
title: Add hive_with_tickets fixture to conftest.py
description: 'Context: Builds on single_hive fixture - pre-creates ticket hierarchy
  for relationship testing.


  Requirements:

  - Create `hive_with_tickets` fixture in conftest.py using `single_hive` fixture

  - Use `@pytest.fixture(scope="function")`

  - Create epic ticket (backend.bees-xxx)

  - Create task ticket with epic as parent

  - Create subtask ticket with task as parent

  - Use create_ticket() functions to ensure proper structure

  - Yield tuple of (repo_root, hive_path, epic_id, task_id, subtask_id)


  Files: conftest.py

  Parent Task: features.bees-l71


  Acceptance: Fixture creates valid epic→task→subtask hierarchy with proper IDs and
  relationships'
up_dependencies:
- features.bees-5v6
parent: features.bees-l71
created_at: '2026-02-05T08:09:39.371474'
updated_at: '2026-02-05T08:14:42.910584'
status: completed
bees_version: '1.1'
---

Context: Builds on single_hive fixture - pre-creates ticket hierarchy for relationship testing.

Requirements:
- Create `hive_with_tickets` fixture in conftest.py using `single_hive` fixture
- Use `@pytest.fixture(scope="function")`
- Create epic ticket (backend.bees-xxx)
- Create task ticket with epic as parent
- Create subtask ticket with task as parent
- Use create_ticket() functions to ensure proper structure
- Yield tuple of (repo_root, hive_path, epic_id, task_id, subtask_id)

Files: conftest.py
Parent Task: features.bees-l71

Acceptance: Fixture creates valid epic→task→subtask hierarchy with proper IDs and relationships
