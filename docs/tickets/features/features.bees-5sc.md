---
id: features.bees-5sc
type: epic
title: 'NAME_SIMPLE: Multi-Hive Ticket Lookup'
description: |
  Rewrite path resolution to scan all hives instead of parsing hive from ID. Update get_ticket_path(), infer_ticket_type_from_id(), and list_tickets(). No caching/indexing.
  
  Acceptance Criteria:
  - User creates ticket in any hive, then runs show_ticket(id) - works correctly
  - User lists all tickets - returns tickets from all hives with new format
  - Agent tests performance with 10+ hives (acceptable without caching per requirement)
  - Agent creates integration tests verifying cross-hive scanning
  
  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
status: open
labels:
- not-started
up_dependencies:
- features.bees-18h
down_dependencies:
- features.bees-1m0
created_at: '2026-02-04T00:47:49.168719'
updated_at: '2026-02-04T00:47:49.168719'
bees_version: '1.1'
---

Rewrite path resolution to scan all hives instead of parsing hive from ID. Update get_ticket_path(), infer_ticket_type_from_id(), and list_tickets(). No caching/indexing.

Acceptance Criteria:
- User creates ticket in any hive, then runs show_ticket(id) - works correctly
- User lists all tickets - returns tickets from all hives with new format
- Agent tests performance with 10+ hives (acceptable without caching per requirement)
- Agent creates integration tests verifying cross-hive scanning

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
