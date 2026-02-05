---
id: features.bees-lhf
type: subtask
title: Register needs_real_git_check marker in pytest configuration
description: 'Context: Need to register the custom pytest marker to avoid warnings
  and enable configuration.


  Requirements:

  - Add marker registration in pytest.ini or conftest.py

  - Use format: `markers = needs_real_git_check: mark test as needing real git repository
  checks`


  Files: pytest.ini or conftest.py (whichever file contains marker configuration)


  Acceptance: Running pytest shows no warnings about unregistered markers'
down_dependencies:
- features.bees-6i0
- features.bees-b6d
- features.bees-ofx
parent: features.bees-27y
created_at: '2026-02-05T12:45:30.711532'
updated_at: '2026-02-05T12:45:52.919055'
status: open
bees_version: '1.1'
---

Context: Need to register the custom pytest marker to avoid warnings and enable configuration.

Requirements:
- Add marker registration in pytest.ini or conftest.py
- Use format: `markers = needs_real_git_check: mark test as needing real git repository checks`

Files: pytest.ini or conftest.py (whichever file contains marker configuration)

Acceptance: Running pytest shows no warnings about unregistered markers
