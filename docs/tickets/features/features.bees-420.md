---
id: features.bees-420
type: subtask
title: Create src/mcp_repo_utils.py with repository root detection functions
description: "Context: Extract repository root detection logic from src/mcp_server.py\
  \ into a dedicated module.\n\nWhat to Create:\n- New file: src/mcp_repo_utils.py\n\
  - Extract and move three functions from src/mcp_server.py (lines 124-253):\n  -\
  \ get_repo_root_from_path() - finds git repo from given path\n  - get_client_repo_root()\
  \ - handles MCP context and roots protocol\n  - get_repo_root() - wrapper with fallback\
  \ logic\n- Include all error handling, logging, and docstrings\n- Add proper imports\
  \ (pathlib, logging, subprocess, fastmcp types)\n\nRequirements:\n- Preserve all\
  \ function signatures exactly\n- Keep all error handling and logging intact\n- Ensure\
  \ logging configuration works in new module\n- Module should be ~150-200 lines\n\
  \nSuccess Criteria:\n- src/mcp_repo_utils.py exists with all three functions\n-\
  \ Functions retain exact behavior from original\n- Logging statements work correctly\n\
  - No syntax or import errors"
down_dependencies:
- features.bees-x3x
- features.bees-sas
- features.bees-at0
parent: features.bees-alr
created_at: '2026-02-03T17:03:00.765099'
updated_at: '2026-02-03T19:20:05.542541'
status: completed
bees_version: '1.1'
---

Context: Extract repository root detection logic from src/mcp_server.py into a dedicated module.

What to Create:
- New file: src/mcp_repo_utils.py
- Extract and move three functions from src/mcp_server.py (lines 124-253):
  - get_repo_root_from_path() - finds git repo from given path
  - get_client_repo_root() - handles MCP context and roots protocol
  - get_repo_root() - wrapper with fallback logic
- Include all error handling, logging, and docstrings
- Add proper imports (pathlib, logging, subprocess, fastmcp types)

Requirements:
- Preserve all function signatures exactly
- Keep all error handling and logging intact
- Ensure logging configuration works in new module
- Module should be ~150-200 lines

Success Criteria:
- src/mcp_repo_utils.py exists with all three functions
- Functions retain exact behavior from original
- Logging statements work correctly
- No syntax or import errors
