---
id: features.bees-d3s
type: epic
title: Put ticket IDs in [] to make them more clear in the index
description: '## Problem

  Currently, ticket IDs in the index are displayed inline without clear visual separation,
  making them harder to scan and distinguish from the ticket titles.


  ## Proposed Solution

  Format ticket IDs in the index with square brackets (e.g., `[features.bees-abc]`)
  to:

  - Create clear visual separation between ID and title

  - Make IDs easier to scan and copy

  - Follow common convention for reference formatting


  ## Example

  **Current:**

  ```

  features.bees-abc Implement user authentication

  ```


  **Proposed:**

  ```

  [features.bees-abc] Implement user authentication

  ```


  ## Scope

  - Update index generation logic to wrap ticket IDs in brackets

  - Ensure formatting works across all ticket types (epic, task, subtask)

  - Verify markdown rendering looks clean'
status: open
created_at: '2026-02-03T06:58:03.129508'
updated_at: '2026-02-03T06:58:03.129513'
bees_version: '1.1'
---

## Problem
Currently, ticket IDs in the index are displayed inline without clear visual separation, making them harder to scan and distinguish from the ticket titles.

## Proposed Solution
Format ticket IDs in the index with square brackets (e.g., `[features.bees-abc]`) to:
- Create clear visual separation between ID and title
- Make IDs easier to scan and copy
- Follow common convention for reference formatting

## Example
**Current:**
```
features.bees-abc Implement user authentication
```

**Proposed:**
```
[features.bees-abc] Implement user authentication
```

## Scope
- Update index generation logic to wrap ticket IDs in brackets
- Ensure formatting works across all ticket types (epic, task, subtask)
- Verify markdown rendering looks clean
