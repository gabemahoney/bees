---
id: features.bees-u9o
type: task
title: Create storage.md
description: 'Extract storage architecture covering hive directory structure, identity
  markers, ticket schema, and flat storage.


  Context: Storage concepts (hive directories, identity markers, ticket IDs, flat
  storage) are tightly related but scattered across master_plan.md with excessive
  detail.


  What Needs to Change:

  - Create docs/architecture/storage.md

  - Extract "Hive Directory Structure" section

  - Extract identity marker format and purpose

  - Extract "Ticket Schema Versioning" section

  - Extract "Flat Storage Architecture" section

  - Extract "Hive ID System" section

  - Remove implementation step-by-step details


  Success Criteria:

  - Document is under 3k tokens

  - Explains hive directory layout (eggs/, evicted/, .hive/)

  - Covers identity marker purpose and recovery

  - Explains ticket ID format and namespacing

  - Explains flat storage rationale


  Files: docs/architecture/storage.md (new), docs/plans/master_plan.md (source)

  Epic: features.bees-bl8'
down_dependencies:
- features.bees-gzx
parent: features.bees-bl8
children:
- features.bees-gau
- features.bees-3q9
created_at: '2026-02-03T16:51:59.640269'
updated_at: '2026-02-03T17:23:13.307662'
priority: 0
status: completed
bees_version: '1.1'
---

Extract storage architecture covering hive directory structure, identity markers, ticket schema, and flat storage.

Context: Storage concepts (hive directories, identity markers, ticket IDs, flat storage) are tightly related but scattered across master_plan.md with excessive detail.

What Needs to Change:
- Create docs/architecture/storage.md
- Extract "Hive Directory Structure" section
- Extract identity marker format and purpose
- Extract "Ticket Schema Versioning" section
- Extract "Flat Storage Architecture" section
- Extract "Hive ID System" section
- Remove implementation step-by-step details

Success Criteria:
- Document is under 3k tokens
- Explains hive directory layout (eggs/, evicted/, .hive/)
- Covers identity marker purpose and recovery
- Explains ticket ID format and namespacing
- Explains flat storage rationale

Files: docs/architecture/storage.md (new), docs/plans/master_plan.md (source)
Epic: features.bees-bl8
