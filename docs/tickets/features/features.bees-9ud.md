---
id: features.bees-9ud
type: subtask
title: Add fixture hierarchy documentation to conftest.py module docstring
description: "Context: Developers need an overview of fixture relationships and dependencies\
  \ before diving into individual fixtures.\n\nWhat to document:\n- Expand module-level\
  \ docstring in tests/conftest.py\n- Create a \"Fixture Overview\" section explaining:\n\
  \  * Autouse fixtures that apply to all tests (3 fixtures)\n  * Opt-in fixtures\
  \ for specific test needs (3 fixtures)\n  * Fixture dependency hierarchy/relationships\n\
  - Add a \"Quick Start Guide\" showing common test patterns:\n  * Simple unit test\
  \ (uses autouse fixtures only)\n  * Integration test needing isolated environment\
  \ (use isolated_bees_env)\n  * Testing MCP functions (use mock_mcp_context)\n  *\
  \ Testing core functions with context (use repo_root_ctx)\n- Add decision tree for\
  \ choosing the right fixture\n\nFiles: tests/conftest.py (lines 1-9, expand this\
  \ section)\n\nAcceptance: Module docstring contains overview, fixture categories,\
  \ relationship diagram, quick start patterns, and decision tree."
parent: features.bees-m6i
created_at: '2026-02-05T08:10:00.133726'
updated_at: '2026-02-05T08:24:42.204520'
status: completed
bees_version: '1.1'
---

Context: Developers need an overview of fixture relationships and dependencies before diving into individual fixtures.

What to document:
- Expand module-level docstring in tests/conftest.py
- Create a "Fixture Overview" section explaining:
  * Autouse fixtures that apply to all tests (3 fixtures)
  * Opt-in fixtures for specific test needs (3 fixtures)
  * Fixture dependency hierarchy/relationships
- Add a "Quick Start Guide" showing common test patterns:
  * Simple unit test (uses autouse fixtures only)
  * Integration test needing isolated environment (use isolated_bees_env)
  * Testing MCP functions (use mock_mcp_context)
  * Testing core functions with context (use repo_root_ctx)
- Add decision tree for choosing the right fixture

Files: tests/conftest.py (lines 1-9, expand this section)

Acceptance: Module docstring contains overview, fixture categories, relationship diagram, quick start patterns, and decision tree.
