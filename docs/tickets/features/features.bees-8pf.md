---
id: features.bees-8pf
type: subtask
title: Scan test files and remove redundant get_repo_root_from_path patches
description: 'Context: With centralized mocking in conftest.py, individual test files
  no longer need to patch get_repo_root_from_path.


  Requirements:

  - Search all files in tests/ for patches of get_repo_root_from_path

  - Remove redundant @patch decorators and patch context managers

  - Verify tests still pass after removal

  - Leave patches that serve a specific purpose (testing error conditions, etc.)


  Reference: Task features.bees-tv7

  Files: tests/**/*.py


  Acceptance:

  - No redundant patches remain in test files

  - Tests run successfully without individual patches'
down_dependencies:
- features.bees-o3k
parent: features.bees-tv7
created_at: '2026-02-05T12:46:03.346632'
updated_at: '2026-02-05T12:46:16.500534'
status: open
bees_version: '1.1'
---

Context: With centralized mocking in conftest.py, individual test files no longer need to patch get_repo_root_from_path.

Requirements:
- Search all files in tests/ for patches of get_repo_root_from_path
- Remove redundant @patch decorators and patch context managers
- Verify tests still pass after removal
- Leave patches that serve a specific purpose (testing error conditions, etc.)

Reference: Task features.bees-tv7
Files: tests/**/*.py

Acceptance:
- No redundant patches remain in test files
- Tests run successfully without individual patches
