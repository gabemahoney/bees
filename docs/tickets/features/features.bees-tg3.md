---
id: features.bees-tg3
type: subtask
title: Document session-scoped fixtures (backup_project_config)
description: 'Context: The backup_project_config fixture needs comprehensive documentation
  explaining its purpose and behavior.


  What to document:

  - Add detailed docstring to backup_project_config fixture

  - Explain why this is session-scoped and autouse

  - Document that it backs up .bees/config.json before tests and restores after

  - Include usage example showing how it prevents test pollution

  - Explain when developers would rely on this (all tests automatically)


  Files: tests/conftest.py (lines 11-27)


  Acceptance: Docstring includes purpose, scope explanation, backup/restore behavior,
  and usage context.'
parent: features.bees-m6i
created_at: '2026-02-05T08:09:39.061708'
updated_at: '2026-02-05T08:23:58.617798'
status: completed
bees_version: '1.1'
---

Context: The backup_project_config fixture needs comprehensive documentation explaining its purpose and behavior.

What to document:
- Add detailed docstring to backup_project_config fixture
- Explain why this is session-scoped and autouse
- Document that it backs up .bees/config.json before tests and restores after
- Include usage example showing how it prevents test pollution
- Explain when developers would rely on this (all tests automatically)

Files: tests/conftest.py (lines 11-27)

Acceptance: Docstring includes purpose, scope explanation, backup/restore behavior, and usage context.
