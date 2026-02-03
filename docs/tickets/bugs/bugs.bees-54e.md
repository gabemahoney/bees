---
id: bugs.bees-54e
type: task
title: Add integration test in test_pipeline.py for parent= search term
description: 'Context: Currently test_pipeline.py has fixtures with parent relationships
  but no test cases that verify `parent=` works in the full pipeline execution. Only
  unit tests exist for parser and executor separately.


  What Needs to Change:

  - Add integration test case in test_pipeline.py that exercises parent= through full
  query pipeline

  - Use existing fixtures with parent relationships

  - Verify parent= filter works correctly in end-to-end execution

  - Test both single parent= filter and combined with other filters


  Why: Ensures parent= search term works correctly through the entire pipeline, not
  just in isolated unit tests.


  Success Criteria:

  - New integration test in test_pipeline.py passes

  - Test uses real fixtures and exercises full pipeline

  - Test covers both single and combined filter scenarios


  Epic: bugs.bees-d3o'
labels:
- test
up_dependencies:
- bugs.bees-yom
parent: bugs.bees-d3o
children:
- bugs.bees-sj6
- bugs.bees-mad
- bugs.bees-0qz
- bugs.bees-7mv
created_at: '2026-02-03T07:27:44.933945'
updated_at: '2026-02-03T07:30:06.536254'
priority: 1
status: completed
bees_version: '1.1'
---

Context: Currently test_pipeline.py has fixtures with parent relationships but no test cases that verify `parent=` works in the full pipeline execution. Only unit tests exist for parser and executor separately.

What Needs to Change:
- Add integration test case in test_pipeline.py that exercises parent= through full query pipeline
- Use existing fixtures with parent relationships
- Verify parent= filter works correctly in end-to-end execution
- Test both single parent= filter and combined with other filters

Why: Ensures parent= search term works correctly through the entire pipeline, not just in isolated unit tests.

Success Criteria:
- New integration test in test_pipeline.py passes
- Test uses real fixtures and exercises full pipeline
- Test covers both single and combined filter scenarios

Epic: bugs.bees-d3o
