---
id: features.bees-ev2
type: epic
title: Index should list tasks under their epics and subtasks under their tasks. Like
  a tree view
description: "## Problem\nCurrently, the index displays tickets in flat sections (Epics,\
  \ Tasks, Subtasks), making it difficult to:\n- Understand the relationship between\
  \ parent and child tickets\n- See the full hierarchy at a glance\n- Navigate from\
  \ epic to its tasks to their subtasks\n\n## Proposed Solution\nRestructure the index\
  \ to display tickets in a hierarchical tree view where:\n- Epics are top-level entries\n\
  - Tasks are nested under their parent epic (with indentation)\n- Subtasks are nested\
  \ under their parent task (with deeper indentation)\n\n## Example\n**Current:**\n\
  ```\n## Epics\n- features.bees-abc: User authentication\n\n## Tasks\n- features.bees-def:\
  \ Implement login form (parent: features.bees-abc)\n- features.bees-ghi: Add password\
  \ hashing (parent: features.bees-abc)\n\n## Subtasks\n- features.bees-jkl: Create\
  \ login component (parent: features.bees-def)\n```\n\n**Proposed:**\n```\n## Epics\n\
  \n- features.bees-abc: User authentication\n  - features.bees-def: Implement login\
  \ form\n    - features.bees-jkl: Create login component\n  - features.bees-ghi:\
  \ Add password hashing\n```\n\n## Scope\n- Update index generation to build hierarchical\
  \ structure\n- Handle orphaned tasks/subtasks (tickets without valid parents)\n\
  - Maintain backward compatibility with markdown links\n- Consider indentation style\
  \ (spaces, bullets, etc.)"
status: open
created_at: '2026-02-03T06:59:14.719259'
updated_at: '2026-02-03T06:59:14.719261'
bees_version: '1.1'
---

## Problem
Currently, the index displays tickets in flat sections (Epics, Tasks, Subtasks), making it difficult to:
- Understand the relationship between parent and child tickets
- See the full hierarchy at a glance
- Navigate from epic to its tasks to their subtasks

## Proposed Solution
Restructure the index to display tickets in a hierarchical tree view where:
- Epics are top-level entries
- Tasks are nested under their parent epic (with indentation)
- Subtasks are nested under their parent task (with deeper indentation)

## Example
**Current:**
```
## Epics
- features.bees-abc: User authentication

## Tasks
- features.bees-def: Implement login form (parent: features.bees-abc)
- features.bees-ghi: Add password hashing (parent: features.bees-abc)

## Subtasks
- features.bees-jkl: Create login component (parent: features.bees-def)
```

**Proposed:**
```
## Epics

- features.bees-abc: User authentication
  - features.bees-def: Implement login form
    - features.bees-jkl: Create login component
  - features.bees-ghi: Add password hashing
```

## Scope
- Update index generation to build hierarchical structure
- Handle orphaned tasks/subtasks (tickets without valid parents)
- Maintain backward compatibility with markdown links
- Consider indentation style (spaces, bullets, etc.)
