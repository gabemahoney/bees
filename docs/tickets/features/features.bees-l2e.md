---
id: features.bees-l2e
type: subtask
title: Update README.md with mcp_id_utils module documentation
description: 'Context: Document the new mcp_id_utils module in README.md after extracting
  ID parsing utilities from mcp_server.py.


  Requirements:

  - Add section describing mcp_id_utils module purpose (ID parsing utilities)

  - Document parse_ticket_id() function with parameters and return type

  - Document parse_hive_from_ticket_id() function with parameters and return type

  - Include brief usage examples showing how to parse ticket IDs

  - Explain why these utilities are separate (prevent circular dependencies)


  Files: README.md


  Acceptance Criteria:

  - README.md contains mcp_id_utils section

  - Both functions documented with signatures and examples

  - Documentation explains module purpose and design rationale'
parent: features.bees-pt9
up_dependencies:
- features.bees-jc5
status: open
created_at: '2026-02-03T17:03:14.520365'
updated_at: '2026-02-03T17:03:14.520368'
bees_version: '1.1'
---

Context: Document the new mcp_id_utils module in README.md after extracting ID parsing utilities from mcp_server.py.

Requirements:
- Add section describing mcp_id_utils module purpose (ID parsing utilities)
- Document parse_ticket_id() function with parameters and return type
- Document parse_hive_from_ticket_id() function with parameters and return type
- Include brief usage examples showing how to parse ticket IDs
- Explain why these utilities are separate (prevent circular dependencies)

Files: README.md

Acceptance Criteria:
- README.md contains mcp_id_utils section
- Both functions documented with signatures and examples
- Documentation explains module purpose and design rationale
