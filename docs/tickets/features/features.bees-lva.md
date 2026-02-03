---
id: features.bees-lva
type: subtask
title: Add test for _show_ticket with explicit repo_root parameter
description: 'Add test_show_ticket_with_explicit_repo_root() to tests/test_mcp_roots.py
  that verifies _show_ticket accepts and uses the explicit repo_root parameter when
  ctx=None.


  Context: _show_ticket was modified to accept repo_root parameter but lacks test
  coverage.


  Requirements:

  - Test should call _show_ticket with repo_root=str(test_repo) and ctx=None

  - Should verify repo_root is used by attempting to show a nonexistent ticket

  - Should validate the appropriate error is raised (ticket not found)


  Acceptance: Test passes and validates repo_root parameter works for _show_ticket.'
parent: features.bees-v4d
created_at: '2026-02-03T12:42:57.709907'
updated_at: '2026-02-03T13:02:13.730051'
status: completed
bees_version: '1.1'
---

Add test_show_ticket_with_explicit_repo_root() to tests/test_mcp_roots.py that verifies _show_ticket accepts and uses the explicit repo_root parameter when ctx=None.

Context: _show_ticket was modified to accept repo_root parameter but lacks test coverage.

Requirements:
- Test should call _show_ticket with repo_root=str(test_repo) and ctx=None
- Should verify repo_root is used by attempting to show a nonexistent ticket
- Should validate the appropriate error is raised (ticket not found)

Acceptance: Test passes and validates repo_root parameter works for _show_ticket.
