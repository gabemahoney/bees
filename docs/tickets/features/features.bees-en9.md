---
id: features.bees-en9
type: epic
title: 'NAME_SIMPLE: Migrate Bees Repo Tickets to New Format'
description: |
  Build migration tooling to convert bees repo tickets from {hive}.bees-{3char} to bees.{4char} format. Scan all existing tickets, generate new IDs, rename files, update all references.
  
  Acceptance Criteria:
  - Agent runs migration script on bees repo
  - All ticket files renamed from old to new format (e.g., features.bees-abc.md → bees.aB3x.md)
  - All parent/children/dependency references updated throughout all tickets
  - Agent validates: all tickets loadable, all relationships bidirectional, no broken references
  - User can run list_tickets() and see all migrated tickets with new IDs
  - Documentation updated with migration steps for reference
  
  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
status: open
labels:
- not-started
up_dependencies:
- features.bees-1m0
created_at: '2026-02-04T00:47:49.168719'
updated_at: '2026-02-04T00:47:49.168719'
bees_version: '1.1'
---

Build migration tooling to convert bees repo tickets from {hive}.bees-{3char} to bees.{4char} format. Scan all existing tickets, generate new IDs, rename files, update all references.

Acceptance Criteria:
- Agent runs migration script on bees repo
- All ticket files renamed from old to new format (e.g., features.bees-abc.md → bees.aB3x.md)
- All parent/children/dependency references updated throughout all tickets
- Agent validates: all tickets loadable, all relationships bidirectional, no broken references
- User can run list_tickets() and see all migrated tickets with new IDs
- Documentation updated with migration steps for reference

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
