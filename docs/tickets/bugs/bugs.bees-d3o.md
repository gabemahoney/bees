---
id: bugs.bees-d3o
type: epic
title: 'Query error: parent= not supported as search term, only as graph traversal'
description: "## Problem\nWhen attempting to query for tasks by parent ID using `parent=features.bees-d3s`,\
  \ the query fails with:\n\n```\nInvalid query structure: Stage 0: Unknown term 'parent=features.bees-d3s'.\
  \ \nValid search terms: id=, label~, title~, type=. \nValid graph terms: up_dependencies,\
  \ children, parent, down_dependencies\n```\n\n## Analysis\nThe error message indicates\
  \ that `parent` is only available as a graph traversal term (like `children`, `up_dependencies`),\
  \ not as a search term with `=` syntax.\n\nThis means you cannot directly search\
  \ for \"all tasks with parent X\" in a single stage. You must:\n1. First get the\
  \ parent ticket by ID\n2. Then traverse to its children\n\n## Impact\n- Unintuitive\
  \ query design - users expect to be able to filter by parent ID\n- Forces two-stage\
  \ queries when one logical stage should suffice\n- Error message is helpful but\
  \ reveals API limitation\n\n## Possible Solutions\n1. Add `parent=` as a valid search\
  \ term alongside `id=`, `type=`, etc.\n2. Improve documentation to clarify this\
  \ limitation upfront\n3. Add examples showing the correct two-stage approach"
children:
- bugs.bees-yom
- bugs.bees-jpp
- bugs.bees-54e
created_at: '2026-02-03T07:16:19.407578'
updated_at: '2026-02-03T12:05:07.559503'
priority: 2
status: completed
bees_version: '1.1'
---

## Problem
When attempting to query for tasks by parent ID using `parent=features.bees-d3s`, the query fails with:

```
Invalid query structure: Stage 0: Unknown term 'parent=features.bees-d3s'. 
Valid search terms: id=, label~, title~, type=. 
Valid graph terms: up_dependencies, children, parent, down_dependencies
```

## Analysis
The error message indicates that `parent` is only available as a graph traversal term (like `children`, `up_dependencies`), not as a search term with `=` syntax.

This means you cannot directly search for "all tasks with parent X" in a single stage. You must:
1. First get the parent ticket by ID
2. Then traverse to its children

## Impact
- Unintuitive query design - users expect to be able to filter by parent ID
- Forces two-stage queries when one logical stage should suffice
- Error message is helpful but reveals API limitation

## Possible Solutions
1. Add `parent=` as a valid search term alongside `id=`, `type=`, etc.
2. Improve documentation to clarify this limitation upfront
3. Add examples showing the correct two-stage approach
