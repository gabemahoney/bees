---
id: bugs.bees-yom
type: task
title: Add parent= as a valid search term in query engine
description: 'Context: Users expect to filter tickets by parent ID using `parent=`
  syntax similar to `id=` and `type=`. Currently parent is only available as a graph
  traversal term, forcing unintuitive two-stage queries.


  What Needs to Change:

  - Locate query parser/validator that defines valid search terms

  - Add `parent=` to the list of valid search terms alongside `id=`, `type=`, `label~`,
  `title~`

  - Implement search logic to filter tickets by parent field

  - Update validation to allow `parent=<ticket-id>` syntax


  Why: This makes the query API more intuitive and allows users to find "all tasks
  with parent X" in a single query stage.


  Success Criteria:

  - Query `- [''parent=features.bees-d3s'']` returns all tasks with that parent

  - Query `- [''type=task'', ''parent=features.bees-d3s'']` combines filters correctly

  - Error message updated to include `parent=` in valid search terms list


  Epic: bugs.bees-d3o'
down_dependencies:
- bugs.bees-jpp
- bugs.bees-54e
parent: bugs.bees-d3o
children:
- bugs.bees-s3d
- bugs.bees-3k7
- bugs.bees-7ue
- bugs.bees-bcm
- bugs.bees-fmj
- bugs.bees-sil
- bugs.bees-r6n
- bugs.bees-9eu
- bugs.bees-lya
created_at: '2026-02-03T07:17:31.161164'
updated_at: '2026-02-03T07:27:44.939417'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Users expect to filter tickets by parent ID using `parent=` syntax similar to `id=` and `type=`. Currently parent is only available as a graph traversal term, forcing unintuitive two-stage queries.

What Needs to Change:
- Locate query parser/validator that defines valid search terms
- Add `parent=` to the list of valid search terms alongside `id=`, `type=`, `label~`, `title~`
- Implement search logic to filter tickets by parent field
- Update validation to allow `parent=<ticket-id>` syntax

Why: This makes the query API more intuitive and allows users to find "all tasks with parent X" in a single query stage.

Success Criteria:
- Query `- ['parent=features.bees-d3s']` returns all tasks with that parent
- Query `- ['type=task', 'parent=features.bees-d3s']` combines filters correctly
- Error message updated to include `parent=` in valid search terms list

Epic: bugs.bees-d3o
