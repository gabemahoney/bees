---
id: features.bees-uey
type: subtask
title: Add unit tests for mcp_id_utils functions
description: 'Context: Add comprehensive unit tests for the extracted ID parsing utilities
  in mcp_id_utils.py.


  Requirements:

  - Create test_mcp_id_utils.py or add to existing test file

  - Test parse_ticket_id() with valid IDs, invalid formats, edge cases

  - Test parse_hive_from_ticket_id() with various ticket ID formats

  - Test error handling for malformed IDs

  - Test type hints are correct

  - Achieve high code coverage for both functions


  Files: tests/test_mcp_id_utils.py (new or existing)


  Acceptance Criteria:

  - All functions in mcp_id_utils.py have unit tests

  - Edge cases and error conditions tested

  - Tests pass with 100% coverage of mcp_id_utils module

  - Test file follows existing test conventions'
parent: features.bees-pt9
up_dependencies:
- features.bees-jc5
status: open
created_at: '2026-02-03T17:03:24.090641'
updated_at: '2026-02-03T17:03:24.090645'
bees_version: '1.1'
---

Context: Add comprehensive unit tests for the extracted ID parsing utilities in mcp_id_utils.py.

Requirements:
- Create test_mcp_id_utils.py or add to existing test file
- Test parse_ticket_id() with valid IDs, invalid formats, edge cases
- Test parse_hive_from_ticket_id() with various ticket ID formats
- Test error handling for malformed IDs
- Test type hints are correct
- Achieve high code coverage for both functions

Files: tests/test_mcp_id_utils.py (new or existing)

Acceptance Criteria:
- All functions in mcp_id_utils.py have unit tests
- Edge cases and error conditions tested
- Tests pass with 100% coverage of mcp_id_utils module
- Test file follows existing test conventions
