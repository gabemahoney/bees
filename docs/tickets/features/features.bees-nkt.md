---
id: features.bees-nkt
type: task
title: Audit and migrate unique test cases from test_writer.py
description: 'Context: test_writer.py is 589 lines of entirely skipped tests. Before
  deletion, we need to ensure no unique test coverage is lost.


  What Needs to Change:

  - Review all test cases in tests/test_writer.py

  - Cross-reference with test_ticket_factory.py, test_reader.py, and MCP integration
  tests

  - Identify any unique test cases not covered elsewhere

  - If gaps exist, add missing tests to appropriate files

  - Run pytest to verify new tests pass


  Why: We must preserve test coverage before deleting the file


  Success Criteria:

  - All unique test cases from test_writer.py are covered in other test files

  - pytest --cov=src shows coverage unchanged or improved

  - Documentation of audit findings


  Files: tests/test_writer.py, tests/test_ticket_factory.py, tests/test_reader.py

  Epic: features.bees-5va'
down_dependencies:
- features.bees-uwi
- features.bees-y9a
- features.bees-h77
- features.bees-qon
- features.bees-ho6
- features.bees-raw
parent: features.bees-5va
children:
- features.bees-xrr
- features.bees-2ao
- features.bees-65m
- features.bees-6a8
created_at: '2026-02-05T09:33:03.597431'
updated_at: '2026-02-05T09:42:55.105534'
priority: 0
status: completed
bees_version: '1.1'
---

Context: test_writer.py is 589 lines of entirely skipped tests. Before deletion, we need to ensure no unique test coverage is lost.

What Needs to Change:
- Review all test cases in tests/test_writer.py
- Cross-reference with test_ticket_factory.py, test_reader.py, and MCP integration tests
- Identify any unique test cases not covered elsewhere
- If gaps exist, add missing tests to appropriate files
- Run pytest to verify new tests pass

Why: We must preserve test coverage before deleting the file

Success Criteria:
- All unique test cases from test_writer.py are covered in other test files
- pytest --cov=src shows coverage unchanged or improved
- Documentation of audit findings

Files: tests/test_writer.py, tests/test_ticket_factory.py, tests/test_reader.py
Epic: features.bees-5va
