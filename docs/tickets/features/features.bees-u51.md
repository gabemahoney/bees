---
id: features.bees-u51
type: subtask
title: Create src/mcp_help.py and extract _help() function
description: 'Context: Extract the help documentation function from mcp_server.py
  to a dedicated module for better maintainability.


  Requirements:

  - Create new file src/mcp_help.py

  - Copy _help() function from src/mcp_server.py (lines 2992-3222, approximately 230
  lines)

  - Preserve all documentation text, formatting, and structure exactly

  - Add proper module imports (typing.Dict, typing.Any)

  - Remove _help() function from src/mcp_server.py


  Files: src/mcp_help.py (new), src/mcp_server.py


  Acceptance Criteria:

  - src/mcp_help.py exists with complete _help() function

  - Function signature and return type unchanged

  - All help text preserved without modifications

  - Original _help() removed from mcp_server.py'
down_dependencies:
- features.bees-72w
- features.bees-ats
- features.bees-f5o
- features.bees-b77
parent: features.bees-jlu
created_at: '2026-02-03T17:03:15.600857'
updated_at: '2026-02-03T17:03:42.399710'
status: open
bees_version: '1.1'
---

Context: Extract the help documentation function from mcp_server.py to a dedicated module for better maintainability.

Requirements:
- Create new file src/mcp_help.py
- Copy _help() function from src/mcp_server.py (lines 2992-3222, approximately 230 lines)
- Preserve all documentation text, formatting, and structure exactly
- Add proper module imports (typing.Dict, typing.Any)
- Remove _help() function from src/mcp_server.py

Files: src/mcp_help.py (new), src/mcp_server.py

Acceptance Criteria:
- src/mcp_help.py exists with complete _help() function
- Function signature and return type unchanged
- All help text preserved without modifications
- Original _help() removed from mcp_server.py
