---
id: bugs.bees-fmj
type: subtask
title: Update README.md with parent= search term documentation
description: '**Context**: After implementing parent= as a search term, we need to
  document this new capability in README.md for users.


  **What to Update**:

  - Update `/Users/gmahoney/projects/bees/README.md` to document the parent= search
  term

  - Add parent= to any section listing available search terms

  - Include examples showing how to use parent= in queries

  - Document that parent= allows filtering tickets by parent ID in a single query
  stage


  **Example Usage to Document**:

  ```yaml

  # Find all tasks with a specific parent

  - [''parent=features.bees-d3s'']


  # Combine with other search terms

  - [''type=task'', ''parent=features.bees-d3s'']

  ```


  **Acceptance Criteria**:

  - README.md includes parent= in search terms list

  - Examples demonstrate parent= usage

  - Documentation is clear and consistent with existing search term docs


  **Reference**: Parent Task bugs.bees-yom'
up_dependencies:
- bugs.bees-s3d
parent: bugs.bees-yom
created_at: '2026-02-03T07:18:50.418190'
updated_at: '2026-02-03T07:22:24.522856'
status: completed
bees_version: '1.1'
---

**Context**: After implementing parent= as a search term, we need to document this new capability in README.md for users.

**What to Update**:
- Update `/Users/gmahoney/projects/bees/README.md` to document the parent= search term
- Add parent= to any section listing available search terms
- Include examples showing how to use parent= in queries
- Document that parent= allows filtering tickets by parent ID in a single query stage

**Example Usage to Document**:
```yaml
# Find all tasks with a specific parent
- ['parent=features.bees-d3s']

# Combine with other search terms
- ['type=task', 'parent=features.bees-d3s']
```

**Acceptance Criteria**:
- README.md includes parent= in search terms list
- Examples demonstrate parent= usage
- Documentation is clear and consistent with existing search term docs

**Reference**: Parent Task bugs.bees-yom
