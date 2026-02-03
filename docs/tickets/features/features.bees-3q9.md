---
id: features.bees-3q9
type: subtask
title: Remove extracted storage sections from master_plan.md
description: "Clean up master_plan.md by removing sections that have been extracted\
  \ to storage.md and adding cross-reference.\n\nContext: After extracting storage\
  \ architecture to dedicated doc, need to remove duplicated content from master_plan.md\
  \ to reduce size and maintain single source of truth.\n\nRemove these sections from\
  \ master_plan.md:\n- \"Hive Directory Structure\" section\n- Identity marker format\
  \ details\n- \"Ticket Schema Versioning\" section  \n- \"Flat Storage Architecture\"\
  \ section\n- \"Hive ID System\" section\n\nAdd cross-reference:\n- Where storage\
  \ sections were removed, add: \"See docs/architecture/storage.md for hive directory\
  \ structure, identity markers, ticket schema, and flat storage design.\"\n\nRequirements:\n\
  - Remove only sections extracted to storage.md\n- Preserve any storage content still\
  \ relevant to master_plan context\n- Add clear cross-reference pointer\n- Maintain\
  \ markdown structure and flow\n\nFiles:\n- Edit: docs/plans/master_plan.md\n- Reference:\
  \ docs/architecture/storage.md\n\nAcceptance Criteria:\n- All extracted sections\
  \ removed from master_plan.md\n- Cross-reference added\n- Document remains coherent\n\
  - No broken internal links"
parent: features.bees-u9o
up_dependencies:
- features.bees-gau
status: open
created_at: '2026-02-03T16:53:00.442783'
updated_at: '2026-02-03T16:53:00.442787'
bees_version: '1.1'
---

Clean up master_plan.md by removing sections that have been extracted to storage.md and adding cross-reference.

Context: After extracting storage architecture to dedicated doc, need to remove duplicated content from master_plan.md to reduce size and maintain single source of truth.

Remove these sections from master_plan.md:
- "Hive Directory Structure" section
- Identity marker format details
- "Ticket Schema Versioning" section  
- "Flat Storage Architecture" section
- "Hive ID System" section

Add cross-reference:
- Where storage sections were removed, add: "See docs/architecture/storage.md for hive directory structure, identity markers, ticket schema, and flat storage design."

Requirements:
- Remove only sections extracted to storage.md
- Preserve any storage content still relevant to master_plan context
- Add clear cross-reference pointer
- Maintain markdown structure and flow

Files:
- Edit: docs/plans/master_plan.md
- Reference: docs/architecture/storage.md

Acceptance Criteria:
- All extracted sections removed from master_plan.md
- Cross-reference added
- Document remains coherent
- No broken internal links
