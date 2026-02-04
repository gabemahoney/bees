---
id: features.bees-f0o
type: subtask
title: Update README.md with mcp_query_ops.py module documentation
description: "Context: Document the new mcp_query_ops.py module in the README to help\
  \ users understand the modular architecture.\n\nImplementation Steps:\n1. Locate\
  \ the module architecture section in README.md\n2. Add entry for mcp_query_ops.py:\n\
  \   - Module name and line count\n   - Purpose: Query operations (add named query,\
  \ execute queries)\n   - Key functions: _add_named_query, _execute_query, _execute_freeform_query\n\
  3. Update any references to query operations in mcp_server.py to mention mcp_query_ops.py\n\
  4. Ensure the module fits into the overall architecture description\n\nFiles Affected:\n\
  - README.md\n\nAcceptance Criteria:\n- README.md updated with mcp_query_ops.py documentation\n\
  - Module purpose clearly explained\n- Fits consistently with other module documentation\n\
  - No broken references\n\nParent Task: features.bees-txe"
parent: features.bees-txe
up_dependencies:
- features.bees-af3
status: closed
created_at: '2026-02-03T17:03:24.411392'
updated_at: '2026-02-03T17:03:24.411397'
bees_version: '1.1'
---

Context: Document the new mcp_query_ops.py module in the README to help users understand the modular architecture.

Implementation Steps:
1. Locate the module architecture section in README.md
2. Add entry for mcp_query_ops.py:
   - Module name and line count
   - Purpose: Query operations (add named query, execute queries)
   - Key functions: _add_named_query, _execute_query, _execute_freeform_query
3. Update any references to query operations in mcp_server.py to mention mcp_query_ops.py
4. Ensure the module fits into the overall architecture description

Files Affected:
- README.md

Acceptance Criteria:
- README.md updated with mcp_query_ops.py documentation
- Module purpose clearly explained
- Fits consistently with other module documentation
- No broken references

Parent Task: features.bees-txe
