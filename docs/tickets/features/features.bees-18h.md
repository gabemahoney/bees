---
id: features.bees-18h
type: epic
title: 'NAME_SIMPLE: New Ticket ID Format - 4-Character Case-Sensitive'
description: |
  Update ID generation from {hive}.bees-{3lowercase} to {repo}.{4alphanumeric}. Expand charset from 36 chars to 62 (a-z, A-Z, 0-9). Keep collision detection. Read repo_name from client config.
  
  Acceptance Criteria:
  - User creates new ticket via MCP, filename is myproject.aB3x.md format
  - ID uses 4 case-sensitive chars (verifiable by creating multiple tickets)
  - Collision detection still works (agent tests with mocked collisions)
  - Agent creates unit tests validating ID format and charset
  
  Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
status: open
labels:
- not-started
up_dependencies:
- features.bees-bxg
down_dependencies:
- features.bees-5sc
created_at: '2026-02-04T00:47:49.168719'
updated_at: '2026-02-04T00:47:49.168719'
bees_version: '1.1'
---

Update ID generation from {hive}.bees-{3lowercase} to {repo}.{4alphanumeric}. Expand charset from 36 chars to 62 (a-z, A-Z, 0-9). Keep collision detection. Read repo_name from client config.

Acceptance Criteria:
- User creates new ticket via MCP, filename is myproject.aB3x.md format
- ID uses 4 case-sensitive chars (verifiable by creating multiple tickets)
- Collision detection still works (agent tests with mocked collisions)
- Agent creates unit tests validating ID format and charset

Source: /Users/gmahoney/projects/bees/docs/tickets/features/eggs/-1_simplified_naming/PRD.md
