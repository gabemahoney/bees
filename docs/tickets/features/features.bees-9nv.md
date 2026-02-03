---
id: features.bees-9nv
type: subtask
title: Update README.md with repo_root parameter documentation
description: 'Add documentation to README.md explaining the repo_root parameter and
  when MCP clients need to use it.


  Context: Users of MCP clients that don''t support the roots protocol need to understand
  how to provide repo_root explicitly. This should be documented in the main README.


  Requirements:

  - Add a section explaining MCP roots protocol support

  - Document which tools require repo_root parameter

  - Provide examples showing both usage patterns (with/without repo_root)

  - Explain when explicit repo_root is needed (MCP clients without roots protocol
  support)


  Files: README.md


  Parent Task: features.bees-61r (Update MCP tool docstrings to document repo_root
  fallback)


  Acceptance: README.md contains clear documentation about repo_root parameter and
  when to use it.'
parent: features.bees-61r
up_dependencies:
- features.bees-6sr
status: open
created_at: '2026-02-03T06:58:16.467352'
updated_at: '2026-02-03T06:58:16.467356'
bees_version: '1.1'
---

Add documentation to README.md explaining the repo_root parameter and when MCP clients need to use it.

Context: Users of MCP clients that don't support the roots protocol need to understand how to provide repo_root explicitly. This should be documented in the main README.

Requirements:
- Add a section explaining MCP roots protocol support
- Document which tools require repo_root parameter
- Provide examples showing both usage patterns (with/without repo_root)
- Explain when explicit repo_root is needed (MCP clients without roots protocol support)

Files: README.md

Parent Task: features.bees-61r (Update MCP tool docstrings to document repo_root fallback)

Acceptance: README.md contains clear documentation about repo_root parameter and when to use it.
