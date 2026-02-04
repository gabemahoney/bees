---
id: features.bees-c4r
type: task
title: Remove mcp_repo_utils details from README.md
description: '**Context**: README.md lines 21-27 contain "Repository Root Detection"
  section documenting the internal mcp_repo_utils.py module with function names and
  implementation details. This violates README best practices: users don''t need to
  know about internal modules.


  **What to do**:

  - Remove the "Repository Root Detection" section from README.md (lines 21-27)

  - Keep README focused on installation and usage only

  - Implementation details remain in docs/architecture/mcp_server.md


  **Why**: README should be user-facing only. Internal architecture belongs in architecture
  docs.


  **Files**: README.md'
labels:
- bug
up_dependencies:
- features.bees-alr
parent: features.bees-d6o
children:
- features.bees-u2o
created_at: '2026-02-03T19:26:22.361852'
updated_at: '2026-02-03T19:28:05.253368'
priority: 1
status: completed
bees_version: '1.1'
---

**Context**: README.md lines 21-27 contain "Repository Root Detection" section documenting the internal mcp_repo_utils.py module with function names and implementation details. This violates README best practices: users don't need to know about internal modules.

**What to do**:
- Remove the "Repository Root Detection" section from README.md (lines 21-27)
- Keep README focused on installation and usage only
- Implementation details remain in docs/architecture/mcp_server.md

**Why**: README should be user-facing only. Internal architecture belongs in architecture docs.

**Files**: README.md
