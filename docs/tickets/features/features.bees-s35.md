---
id: features.bees-s35
type: subtask
title: Update README.md with mcp_relationships.py module documentation
description: 'Context: New module src/mcp_relationships.py has been extracted. Update
  README to document this architectural change.


  What to Add:

  - Add entry in architecture/module section describing mcp_relationships.py

  - Document that it handles bidirectional relationship synchronization

  - Explain it''s used by ticket update/delete operations

  - Note the 9 functions it contains


  Files: README.md


  Acceptance Criteria:

  - README.md mentions mcp_relationships.py module

  - Purpose and role clearly documented

  - Consistent with existing documentation style'
up_dependencies:
- features.bees-9ss
down_dependencies:
- features.bees-a90
parent: features.bees-t9t
created_at: '2026-02-03T17:03:12.748818'
updated_at: '2026-02-03T17:03:27.596854'
status: open
bees_version: '1.1'
---

Context: New module src/mcp_relationships.py has been extracted. Update README to document this architectural change.

What to Add:
- Add entry in architecture/module section describing mcp_relationships.py
- Document that it handles bidirectional relationship synchronization
- Explain it's used by ticket update/delete operations
- Note the 9 functions it contains

Files: README.md

Acceptance Criteria:
- README.md mentions mcp_relationships.py module
- Purpose and role clearly documented
- Consistent with existing documentation style
