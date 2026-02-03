---
id: features.bees-lhh
type: subtask
title: Update README.md with mcp_hive_ops.py module documentation
description: 'Context: New mcp_hive_ops.py module extracts hive lifecycle operations.
  README should reflect this architectural change.


  What to Do:

  - Update README.md architecture/structure section if it exists

  - Document that hive lifecycle operations (colonize, list, abandon, rename, sanitize)
  are in src/mcp_hive_ops.py

  - Explain the separation: mcp_hive_ops.py handles hive lifecycle, mcp_hive_utils.py
  handles hive validation/scanning

  - Keep changes minimal - only add what''s necessary for users to understand the
  module organization


  Files: README.md


  Reference: Parent Task features.bees-2hp


  Acceptance Criteria:

  - README reflects new mcp_hive_ops.py module

  - Clear distinction between hive ops and hive utils

  - Documentation is concise and helpful'
parent: features.bees-2hp
up_dependencies:
- features.bees-8jm
status: open
created_at: '2026-02-03T17:03:18.007202'
updated_at: '2026-02-03T17:03:18.007205'
bees_version: '1.1'
---

Context: New mcp_hive_ops.py module extracts hive lifecycle operations. README should reflect this architectural change.

What to Do:
- Update README.md architecture/structure section if it exists
- Document that hive lifecycle operations (colonize, list, abandon, rename, sanitize) are in src/mcp_hive_ops.py
- Explain the separation: mcp_hive_ops.py handles hive lifecycle, mcp_hive_utils.py handles hive validation/scanning
- Keep changes minimal - only add what's necessary for users to understand the module organization

Files: README.md

Reference: Parent Task features.bees-2hp

Acceptance Criteria:
- README reflects new mcp_hive_ops.py module
- Clear distinction between hive ops and hive utils
- Documentation is concise and helpful
