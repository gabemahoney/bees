---
id: bugs.bees-sj6
type: subtask
title: Add integration test for single parent= filter in test_pipeline.py
description: 'Context: Task bugs.bees-54e requires integration tests for parent= search
  term in test_pipeline.py. The fixtures already have parent relationships (bees-tk1
  and bees-tk2 have parent=bees-ep1).


  What to Create:

  - Add test method in TestQueryExecution class

  - Test case: Single stage query with parent= filter

  - Query: [[''parent=bees-ep1'']]

  - Expected: Returns bees-tk1 and bees-tk2

  - Verify full pipeline execution (not just isolated executor)


  Files to Modify:

  - /Users/gmahoney/projects/bees/tests/test_pipeline.py


  Acceptance:

  - Test passes using existing fixtures

  - Test exercises full pipeline through PipelineEvaluator.execute_query()

  - Test verifies correct ticket IDs returned'
down_dependencies:
- bugs.bees-7mv
parent: bugs.bees-54e
created_at: '2026-02-03T07:28:25.390287'
updated_at: '2026-02-03T07:29:18.533738'
status: completed
bees_version: '1.1'
---

Context: Task bugs.bees-54e requires integration tests for parent= search term in test_pipeline.py. The fixtures already have parent relationships (bees-tk1 and bees-tk2 have parent=bees-ep1).

What to Create:
- Add test method in TestQueryExecution class
- Test case: Single stage query with parent= filter
- Query: [['parent=bees-ep1']]
- Expected: Returns bees-tk1 and bees-tk2
- Verify full pipeline execution (not just isolated executor)

Files to Modify:
- /Users/gmahoney/projects/bees/tests/test_pipeline.py

Acceptance:
- Test passes using existing fixtures
- Test exercises full pipeline through PipelineEvaluator.execute_query()
- Test verifies correct ticket IDs returned
