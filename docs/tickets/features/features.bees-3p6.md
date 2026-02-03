---
id: features.bees-3p6
type: task
title: Remove dangerous Path.cwd() fallback from get_config_path()
description: "Remove the broken fallback in get_config_path() that falls back to Path.cwd()\
  \ when repo_root=None. This fallback is fundamentally broken for MCP servers because\
  \ the server runs in the bees project directory, not the client's project.\n\n##\
  \ Current Broken Code (src/config.py:162-165)\n```python\nif repo_root is None:\n\
  \    from .mcp_server import get_repo_root_from_path\n    # For non-MCP usage (tests,\
  \ CLI), try to find git repo from cwd\n    repo_root = get_repo_root_from_path(Path.cwd())\n\
  ```\n\n## Required Fix\nReplace with clear error:\n```python\nif repo_root is None:\n\
  \    raise ValueError(\n        \"repo_root is required. Your MCP client does not\
  \ support the roots protocol. \"\n        \"Please provide repo_root explicitly\
  \ when calling this tool.\"\n    )\n```\n\n## Impact\nAll functions that call get_config_path()\
  \ will inherit this behavior:\n- load_bees_config()\n- save_bees_config()\n- init_bees_config_if_needed()\n\
  - write_hive_config_dict()\n- register_hive_dict()\n- And many others\n\n## CRITICAL:\
  \ Test Requirements\n**YOU MUST fix all broken tests and get the full test suite\
  \ passing before marking this complete.**\n\nRun `poetry run pytest tests/ -v` and\
  \ fix every test that breaks. Tests will need explicit repo_root parameters.\n\n\
  ## Success Criteria\n- ✅ Fallback removed from get_config_path()\n- ✅ Clear error\
  \ message added\n- ✅ ALL tests fixed and passing: `poetry run pytest tests/ -v`\n\
  - ✅ No test uses the broken fallback anymore"
down_dependencies:
- features.bees-4f3
parent: features.bees-h0a
created_at: '2026-02-03T15:43:47.339644'
updated_at: '2026-02-03T16:11:49.704591'
status: open
bees_version: '1.1'
---

Remove the broken fallback in get_config_path() that falls back to Path.cwd() when repo_root=None. This fallback is fundamentally broken for MCP servers because the server runs in the bees project directory, not the client's project.

## Current Broken Code (src/config.py:162-165)
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
All functions that call get_config_path() will inherit this behavior:
- load_bees_config()
- save_bees_config()
- init_bees_config_if_needed()
- write_hive_config_dict()
- register_hive_dict()
- And many others

## CRITICAL: Test Requirements
**YOU MUST fix all broken tests and get the full test suite passing before marking this complete.**

Run `poetry run pytest tests/ -v` and fix every test that breaks. Tests will need explicit repo_root parameters.

## Success Criteria
- ✅ Fallback removed from get_config_path()
- ✅ Clear error message added
- ✅ ALL tests fixed and passing: `poetry run pytest tests/ -v`
- ✅ No test uses the broken fallback anymore
