---
id: features.bees-c0m
type: subtask
title: Update test_mcp_server.py imports to use mcp_id_utils
description: "**Context**: Lines 22-23 of tests/test_mcp_server.py import parse_ticket_id\
  \ and parse_hive_from_ticket_id from mcp_server, but these functions are defined\
  \ in mcp_id_utils.\n\n**What to do**:\n- Open tests/test_mcp_server.py\n- Change\
  \ lines 22-23 from importing through mcp_server\n- Import parse_ticket_id and parse_hive_from_ticket_id\
  \ directly from src.mcp_id_utils instead\n\n**Expected result**: \n- Imports reference\
  \ the actual module where functions are defined\n- No functional changes to test\
  \ behavior\n\n**Files**: tests/test_mcp_server.py"
down_dependencies:
- features.bees-o34
parent: features.bees-yss
created_at: '2026-02-03T19:07:47.579132'
updated_at: '2026-02-03T19:14:22.864483'
status: completed
bees_version: '1.1'
---

**Context**: Lines 22-23 of tests/test_mcp_server.py import parse_ticket_id and parse_hive_from_ticket_id from mcp_server, but these functions are defined in mcp_id_utils.

**What to do**:
- Open tests/test_mcp_server.py
- Change lines 22-23 from importing through mcp_server
- Import parse_ticket_id and parse_hive_from_ticket_id directly from src.mcp_id_utils instead

**Expected result**: 
- Imports reference the actual module where functions are defined
- No functional changes to test behavior

**Files**: tests/test_mcp_server.py
