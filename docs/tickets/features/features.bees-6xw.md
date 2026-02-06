---
id: features.bees-6xw
type: subtask
title: Categorize remaining tool tests (to stay in test_mcp_server.py)
description: 'Context: Remaining ~1,600 lines should stay in test_mcp_server.py covering
  MCP tool operations.


  What to Categorize:

  - Tests in TestUpdateTicket

  - Tests in TestColonizeHiveMCPIntegration

  - Tests in TestColonizeHiveMCPUnit

  - Tests in TestColonizeHiveMCPErrorCases

  - Tests in TestParseTicketId

  - Tests in TestParseHiveFromTicketId

  - Tests in TestUpdateTicketHiveParsing

  - Tests in TestListHives

  - Tests in TestAbandonHive

  - Any other tests not categorized as lifecycle or scan/validate


  Review each test and determine if it tests MCP tools (create_ticket, update_ticket,
  delete_ticket, hive operations, ID parsing, etc.)


  Why: These tests remain in test_mcp_server.py after split.


  Acceptance Criteria:

  - List shows all remaining tool tests with line numbers

  - Estimate total lines ~1,600 (verify against target)

  - Each test has clear rationale for categorization

  - No tests are uncategorized (all 155 accounted for)


  Reference: Task features.bees-4i1

  Files: tests/test_mcp_server.py'
up_dependencies:
- features.bees-ysm
down_dependencies:
- features.bees-p2j
- features.bees-kgk
parent: features.bees-4i1
created_at: '2026-02-05T16:14:11.654278'
updated_at: '2026-02-05T16:20:39.926039'
status: completed
bees_version: '1.1'
---

Context: Remaining ~1,600 lines should stay in test_mcp_server.py covering MCP tool operations.

What to Categorize:
- Tests in TestUpdateTicket
- Tests in TestColonizeHiveMCPIntegration
- Tests in TestColonizeHiveMCPUnit
- Tests in TestColonizeHiveMCPErrorCases
- Tests in TestParseTicketId
- Tests in TestParseHiveFromTicketId
- Tests in TestUpdateTicketHiveParsing
- Tests in TestListHives
- Tests in TestAbandonHive
- Any other tests not categorized as lifecycle or scan/validate

Review each test and determine if it tests MCP tools (create_ticket, update_ticket, delete_ticket, hive operations, ID parsing, etc.)

Why: These tests remain in test_mcp_server.py after split.

Acceptance Criteria:
- List shows all remaining tool tests with line numbers
- Estimate total lines ~1,600 (verify against target)
- Each test has clear rationale for categorization
- No tests are uncategorized (all 155 accounted for)

Reference: Task features.bees-4i1
Files: tests/test_mcp_server.py
