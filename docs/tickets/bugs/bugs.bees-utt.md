---
id: bugs.bees-utt
type: subtask
title: Add integration tests for parent= search term in query pipeline
description: 'Context: Need end-to-end tests that verify parent= works correctly in
  real query execution through the full pipeline.


  What to Test:

  - Test freeform query with parent= filter through MCP server

  - Test parent= combined with other search terms in multi-stage pipeline

  - Test parent= error handling for malformed queries

  - Test parent= with actual ticket fixtures that have parent relationships

  - Verify parent= search results match expected ticket IDs in fixture data


  Where: /Users/gmahoney/projects/bees/tests/test_query_tools.py or /Users/gmahoney/projects/bees/tests/test_pipeline.py


  Use existing integration test patterns with real ticket fixtures.


  Acceptance Criteria:

  - End-to-end query execution with parent= validates correctly

  - Tests use actual ticket fixtures with parent/child relationships

  - Tests verify query results match expected parent-child relationships'
up_dependencies:
- bugs.bees-nbm
down_dependencies:
- bugs.bees-heh
parent: bugs.bees-jpp
created_at: '2026-02-03T07:18:32.000589'
updated_at: '2026-02-03T07:33:06.976419'
status: completed
bees_version: '1.1'
---

Context: Need end-to-end tests that verify parent= works correctly in real query execution through the full pipeline.

What to Test:
- Test freeform query with parent= filter through MCP server
- Test parent= combined with other search terms in multi-stage pipeline
- Test parent= error handling for malformed queries
- Test parent= with actual ticket fixtures that have parent relationships
- Verify parent= search results match expected ticket IDs in fixture data

Where: /Users/gmahoney/projects/bees/tests/test_query_tools.py or /Users/gmahoney/projects/bees/tests/test_pipeline.py

Use existing integration test patterns with real ticket fixtures.

Acceptance Criteria:
- End-to-end query execution with parent= validates correctly
- Tests use actual ticket fixtures with parent/child relationships
- Tests verify query results match expected parent-child relationships
