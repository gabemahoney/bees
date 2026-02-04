---
id: features.bees-w4v
type: task
title: Remove Architecture section from README.md
description: '**Context**: README.md now contains an "Architecture" section (lines
  118-147) with implementation details including Python import statements and internal
  module documentation. This violates README best practices: "README is for human
  users to understand how to install and run the project" and should contain "No implementation
  details in Readme".


  **What to do**:

  - Remove the "Architecture" section from README.md (lines 118-147)

  - Keep README focused on installation and usage only

  - Implementation details remain in docs/architecture/mcp_server.md where they belong


  **Why**: Keeps README clean, focused, and under 1 minute reading time for users.
  Internal architecture belongs in architecture docs.


  **Files**: README.md'
labels:
- bug
up_dependencies:
- features.bees-pt9
parent: features.bees-d6o
children:
- features.bees-968
- features.bees-wvt
created_at: '2026-02-03T19:07:11.240672'
updated_at: '2026-02-03T19:13:49.784954'
priority: 1
status: completed
bees_version: '1.1'
---

**Context**: README.md now contains an "Architecture" section (lines 118-147) with implementation details including Python import statements and internal module documentation. This violates README best practices: "README is for human users to understand how to install and run the project" and should contain "No implementation details in Readme".

**What to do**:
- Remove the "Architecture" section from README.md (lines 118-147)
- Keep README focused on installation and usage only
- Implementation details remain in docs/architecture/mcp_server.md where they belong

**Why**: Keeps README clean, focused, and under 1 minute reading time for users. Internal architecture belongs in architecture docs.

**Files**: README.md
