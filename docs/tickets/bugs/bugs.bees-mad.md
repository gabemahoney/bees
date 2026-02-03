---
id: bugs.bees-mad
type: subtask
title: Add integration test for parent= combined with other filters
description: "Context: Task bugs.bees-54e requires testing parent= search term combined\
  \ with other filters in full pipeline.\n\nWhat to Create:\n- Add test method in\
  \ TestQueryExecution class\n- Test case 1: parent= combined with type=\n  - Query:\
  \ [['parent=bees-ep1', 'type=task']]\n  - Expected: Returns bees-tk1 and bees-tk2\n\
  - Test case 2: parent= combined with label~\n  - Query: [['parent=bees-ep1', 'label~api']]\n\
  \  - Expected: Returns bees-tk1 and bees-tk2 (both have api label)\n- Verify AND\
  \ logic works correctly through full pipeline\n\nFiles to Modify:\n- /Users/gmahoney/projects/bees/tests/test_pipeline.py\n\
  \nAcceptance:\n- Test passes using existing fixtures\n- Test verifies multiple filters\
  \ ANDed correctly\n- Test exercises full pipeline execution"
down_dependencies:
- bugs.bees-7mv
parent: bugs.bees-54e
created_at: '2026-02-03T07:28:30.578085'
updated_at: '2026-02-03T07:29:28.744577'
status: completed
bees_version: '1.1'
---

Context: Task bugs.bees-54e requires testing parent= search term combined with other filters in full pipeline.

What to Create:
- Add test method in TestQueryExecution class
- Test case 1: parent= combined with type=
  - Query: [['parent=bees-ep1', 'type=task']]
  - Expected: Returns bees-tk1 and bees-tk2
- Test case 2: parent= combined with label~
  - Query: [['parent=bees-ep1', 'label~api']]
  - Expected: Returns bees-tk1 and bees-tk2 (both have api label)
- Verify AND logic works correctly through full pipeline

Files to Modify:
- /Users/gmahoney/projects/bees/tests/test_pipeline.py

Acceptance:
- Test passes using existing fixtures
- Test verifies multiple filters ANDed correctly
- Test exercises full pipeline execution
