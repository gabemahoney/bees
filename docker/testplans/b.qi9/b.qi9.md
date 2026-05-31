---
id: b.qi9
type: bee
title: Full Regression Test
parent: null
children:
- t1.qi9.8h
- t1.qi9.w8
- t1.qi9.de
- t1.qi9.4u
- t1.qi9.h5
- t1.qi9.kw
created_at: '2026-02-24T22:45:16.267582'
status: pupa
schema_version: '0.1'
guid: qi96ctjcb5fu4bovny9ibn
reference_materials: null
---
Comprehensive end-to-end release test for bees. Runs in Docker against a clean environment. CLI-first, then MCP server transports.

**Conventions:**
- This runs inside a disposable Docker container. bees uses `~/.bees/config.json` naturally — no `--config` or `--test-config` flags needed (except tests 94-97 which specifically test that feature).
- `$REPO` refers to the working directory (e.g., `/test-repo`)
- When a test says "save the ID", remember the `ticket_id` from the output for use in later tests
- Tests within a phase are sequential — later tests depend on state from earlier ones
- If a test fails, report it and stop. Do not debug or work around the failure.
- **Test Cases must not depend on Test Cases in another Test Area.** Each Test Area is self-contained. Cross-Test Area state dependencies are not allowed.

**Unit test coverage notes:**
- `test_ticket_ids_keyword_accepted` in `tests/test_mcp_ticket_ops.py` (TestBatchUpdate class): regression test verifying that `_update_ticket(ticket_ids=...)` works correctly after the `ticket_id` → `ticket_ids` parameter rename.
