---
id: features.bees-ysm
type: subtask
title: Extract all test function names and line numbers from test_mcp_server.py
description: 'Context: Need complete list of all 155 test functions to categorize
  them accurately.


  What to Do:

  - Use grep or similar to extract all test function names (def test_*) with line
  numbers

  - Capture test class names and their hierarchy

  - Store results in structured format (CSV or JSON) for easy categorization

  - Verify count is exactly 155 tests


  Why: Foundation for accurate categorization; ensures we don''t miss any tests during
  analysis.


  Acceptance Criteria:

  - List contains all 155 test functions with line numbers

  - Test class associations are preserved

  - Data is in structured format ready for categorization


  Reference: Task features.bees-4i1'
down_dependencies:
- features.bees-krd
- features.bees-4e2
- features.bees-6xw
parent: features.bees-4i1
created_at: '2026-02-05T16:13:47.760898'
updated_at: '2026-02-05T16:19:21.446971'
status: completed
bees_version: '1.1'
---

Context: Need complete list of all 155 test functions to categorize them accurately.

What to Do:
- Use grep or similar to extract all test function names (def test_*) with line numbers
- Capture test class names and their hierarchy
- Store results in structured format (CSV or JSON) for easy categorization
- Verify count is exactly 155 tests

Why: Foundation for accurate categorization; ensures we don't miss any tests during analysis.

Acceptance Criteria:
- List contains all 155 test functions with line numbers
- Test class associations are preserved
- Data is in structured format ready for categorization

Reference: Task features.bees-4i1
