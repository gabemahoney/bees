---
id: bugs.bees-9eu
type: subtask
title: Add unit tests for parent= in QueryParser
description: '**Context**: We need unit tests for parent= validation logic in QueryParser
  to ensure it properly validates parent= search terms.


  **What to Create**:

  - Add tests in `/Users/gmahoney/projects/bees/tests/test_query_parser.py`

  - Test that parent= is recognized as a valid search term

  - Test parent= validation logic in _validate_search_term


  **Test Cases to Implement**:

  1. test_parent_search_term_valid - Verify ''parent=bugs.bees-abc'' is valid

  2. test_parent_search_term_empty_value - Verify ''parent='' raises QueryValidationError

  3. test_parent_in_error_message - Verify error message includes ''parent='' in valid
  terms list

  4. test_parent_in_search_stage - Verify parent= can be used in search stage

  5. test_parent_combined_with_other_search_terms - Verify [''type=task'', ''parent=epic-1'']
  works

  6. test_parent_not_mixed_with_graph_terms - Verify [''parent=epic-1'', ''children'']
  raises error (stage purity)


  **Requirements**:

  - Tests use pytest conventions

  - Follow existing test patterns in test_query_parser.py

  - Test both successful validation and error cases

  - Verify error messages are informative


  **Acceptance Criteria**:

  - All test cases pass

  - Tests cover validation logic comprehensively

  - Tests verify parent= works with other search terms

  - Tests verify stage purity rules still apply


  **Reference**: Parent Task bugs.bees-yom, Blocked by bugs.bees-3k7'
up_dependencies:
- bugs.bees-3k7
down_dependencies:
- bugs.bees-lya
parent: bugs.bees-yom
created_at: '2026-02-03T07:19:16.689096'
updated_at: '2026-02-03T07:23:24.214204'
status: completed
bees_version: '1.1'
---

**Context**: We need unit tests for parent= validation logic in QueryParser to ensure it properly validates parent= search terms.

**What to Create**:
- Add tests in `/Users/gmahoney/projects/bees/tests/test_query_parser.py`
- Test that parent= is recognized as a valid search term
- Test parent= validation logic in _validate_search_term

**Test Cases to Implement**:
1. test_parent_search_term_valid - Verify 'parent=bugs.bees-abc' is valid
2. test_parent_search_term_empty_value - Verify 'parent=' raises QueryValidationError
3. test_parent_in_error_message - Verify error message includes 'parent=' in valid terms list
4. test_parent_in_search_stage - Verify parent= can be used in search stage
5. test_parent_combined_with_other_search_terms - Verify ['type=task', 'parent=epic-1'] works
6. test_parent_not_mixed_with_graph_terms - Verify ['parent=epic-1', 'children'] raises error (stage purity)

**Requirements**:
- Tests use pytest conventions
- Follow existing test patterns in test_query_parser.py
- Test both successful validation and error cases
- Verify error messages are informative

**Acceptance Criteria**:
- All test cases pass
- Tests cover validation logic comprehensively
- Tests verify parent= works with other search terms
- Tests verify stage purity rules still apply

**Reference**: Parent Task bugs.bees-yom, Blocked by bugs.bees-3k7
