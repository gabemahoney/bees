---
id: features.bees-gau
type: subtask
title: Create docs/architecture/storage.md with hive structure content
description: 'Create the new storage.md document and extract relevant sections from
  master_plan.md.


  Context: Storage architecture concepts are scattered across master_plan.md with
  excessive implementation details. Need to consolidate into focused architectural
  overview.


  Extract and refactor these sections from master_plan.md:

  - "Hive Directory Structure" section (eggs/, evicted/, .hive/ layout)

  - Identity marker format (.hive/identity.json) and purpose

  - "Ticket Schema Versioning" section (YAML frontmatter, bees_version field)

  - "Flat Storage Architecture" section (rationale for flat storage)

  - "Hive ID System" section (ticket ID format, namespacing)


  Requirements:

  - Focus on architectural decisions and rationale, not implementation steps

  - Remove verbose task-by-task histories

  - Keep document under 3k tokens

  - Explain WHY design decisions were made

  - Use clear markdown structure with headings


  Files:

  - Create: docs/architecture/storage.md

  - Read from: docs/plans/master_plan.md


  Acceptance Criteria:

  - New file created at docs/architecture/storage.md

  - All required storage concepts extracted

  - Document is concise (under 3k tokens)

  - Focuses on design rationale not implementation'
down_dependencies:
- features.bees-3q9
parent: features.bees-u9o
created_at: '2026-02-03T16:52:52.096952'
updated_at: '2026-02-03T16:53:00.448394'
status: open
bees_version: '1.1'
---

Create the new storage.md document and extract relevant sections from master_plan.md.

Context: Storage architecture concepts are scattered across master_plan.md with excessive implementation details. Need to consolidate into focused architectural overview.

Extract and refactor these sections from master_plan.md:
- "Hive Directory Structure" section (eggs/, evicted/, .hive/ layout)
- Identity marker format (.hive/identity.json) and purpose
- "Ticket Schema Versioning" section (YAML frontmatter, bees_version field)
- "Flat Storage Architecture" section (rationale for flat storage)
- "Hive ID System" section (ticket ID format, namespacing)

Requirements:
- Focus on architectural decisions and rationale, not implementation steps
- Remove verbose task-by-task histories
- Keep document under 3k tokens
- Explain WHY design decisions were made
- Use clear markdown structure with headings

Files:
- Create: docs/architecture/storage.md
- Read from: docs/plans/master_plan.md

Acceptance Criteria:
- New file created at docs/architecture/storage.md
- All required storage concepts extracted
- Document is concise (under 3k tokens)
- Focuses on design rationale not implementation
