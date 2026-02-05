---
id: features.bees-yxg
type: subtask
title: Identify and locate port validation tests
description: 'Search test_config.py and test_server.py for all port validation test
  cases. Identify which tests to keep (valid port 1024-65535, invalid port) and which
  to remove. Document current test count and target test count.


  Context: Part of features.bees-115 to reduce port validation test coverage to 2
  essential cases.


  Acceptance: List of test files, current test functions, and decision on which 2
  tests to retain.'
down_dependencies:
- features.bees-ox1
- features.bees-x4q
- features.bees-jf7
parent: features.bees-115
created_at: '2026-02-05T10:20:03.529435'
updated_at: '2026-02-05T10:31:19.197383'
status: completed
bees_version: '1.1'
---

Search test_config.py and test_server.py for all port validation test cases. Identify which tests to keep (valid port 1024-65535, invalid port) and which to remove. Document current test count and target test count.

Context: Part of features.bees-115 to reduce port validation test coverage to 2 essential cases.

Acceptance: List of test files, current test functions, and decision on which 2 tests to retain.
