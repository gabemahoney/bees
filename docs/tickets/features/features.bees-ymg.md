---
id: features.bees-ymg
type: task
title: Remove dangerous Path.cwd() fallback from ensure_bees_dir()
description: "Remove the broken fallback in ensure_bees_dir() that falls back to Path.cwd()\
  \ when repo_root=None. This fallback is fundamentally broken for MCP servers because\
  \ the server runs in the bees project directory, not the client's project.\n\n##\
  \ Current Broken Code (src/config.py:180-183)\n```python\nif repo_root is None:\n\
  \    from .mcp_server import get_repo_root_from_path\n    # For non-MCP usage (tests,\
  \ CLI), try to find git repo from cwd\n    repo_root = get_repo_root_from_path(Path.cwd())\n\
  ```\n\n## Required Fix\nReplace with clear error:\n```python\nif repo_root is None:\n\
  \    raise ValueError(\n        \"repo_root is required. Your MCP client does not\
  \ support the roots protocol. \"\n        \"Please provide repo_root explicitly\
  \ when calling this tool.\"\n    )\n```\n\n## Impact\nAll functions that call ensure_bees_dir()\
  \ will inherit this behavior:\n- save_bees_config()\n- init_bees_config_if_needed()\n\
  - write_hive_config_dict()\n- Any function that creates .bees/ directory\n\n## CRITICAL:\
  \ Test Requirements\n**YOU MUST fix all broken tests and get the full test suite\
  \ passing before marking this complete.**\n\nRun `poetry run pytest tests/ -v` and\
  \ fix every test that breaks. Tests will need explicit repo_root parameters.\n\n\
  ## Success Criteria\n- ✅ Fallback removed from ensure_bees_dir()\n- ✅ Clear error\
  \ message added\n- ✅ ALL tests fixed and passing: `poetry run pytest tests/ -v`\n\
  - ✅ No test uses the broken fallback anymore"
status: completed
created_at: '2026-02-03T15:43:51.737225'
updated_at: '2026-02-03T15:43:51.737229'
bees_version: '1.1'
parent: features.bees-h0a
---

Remove the broken fallback in ensure_bees_dir() that falls back to Path.cwd() when repo_root=None. This fallback is fundamentally broken for MCP servers because the server runs in the bees project directory, not the client's project.

## Current Broken Code (src/config.py:180-183)
```python
if repo_root is None:
    from .mcp_server import get_repo_root_from_path
    # For non-MCP usage (tests, CLI), try to find git repo from cwd
    repo_root = get_repo_root_from_path(Path.cwd())
```

## Required Fix
Replace with clear error:
```python
if repo_root is None:
    raise ValueError(
        "repo_root is required. Your MCP client does not support the roots protocol. "
        "Please provide repo_root explicitly when calling this tool."
    )
```

## Impact
All functions that call ensure_bees_dir() will inherit this behavior:
- save_bees_config()
- init_bees_config_if_needed()
- write_hive_config_dict()
- Any function that creates .bees/ directory

## CRITICAL: Test Requirements
**YOU MUST fix all broken tests and get the full test suite passing before marking this complete.**

Run `poetry run pytest tests/ -v` and fix every test that breaks. Tests will need explicit repo_root parameters.

## Success Criteria
- ✅ Fallback removed from ensure_bees_dir()
- ✅ Clear error message added
- ✅ ALL tests fixed and passing: `poetry run pytest tests/ -v`
- ✅ No test uses the broken fallback anymore
