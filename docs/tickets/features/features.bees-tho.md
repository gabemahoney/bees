---
id: features.bees-tho
type: task
title: Remove duplicate implementation in paths.py
description: "**Context**: paths.py:10-41 contains `_parse_ticket_id_for_path()` which\
  \ duplicates logic from mcp_id_utils.parse_ticket_id(). This violates DRY principle\
  \ and creates maintenance burden.\n\n**What to do**: \n- Update src/paths.py to\
  \ import parse_ticket_id from mcp_id_utils\n- Replace _parse_ticket_id_for_path()\
  \ with direct call to parse_ticket_id()\n- Remove the duplicate implementation\n\
  \n**Why**: Eliminates code duplication and ensures consistent ticket ID parsing\
  \ across codebase.\n\n**Files**: src/paths.py"
labels:
- bug
up_dependencies:
- features.bees-pt9
parent: features.bees-d6o
children:
- features.bees-mnf
- features.bees-71g
- features.bees-2k3
- features.bees-hyk
- features.bees-aqc
created_at: '2026-02-03T19:07:08.707889'
updated_at: '2026-02-03T19:11:56.688123'
priority: 1
status: completed
bees_version: '1.1'
---

**Context**: paths.py:10-41 contains `_parse_ticket_id_for_path()` which duplicates logic from mcp_id_utils.parse_ticket_id(). This violates DRY principle and creates maintenance burden.

**What to do**: 
- Update src/paths.py to import parse_ticket_id from mcp_id_utils
- Replace _parse_ticket_id_for_path() with direct call to parse_ticket_id()
- Remove the duplicate implementation

**Why**: Eliminates code duplication and ensures consistent ticket ID parsing across codebase.

**Files**: src/paths.py
