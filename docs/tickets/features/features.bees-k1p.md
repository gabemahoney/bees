---
id: features.bees-k1p
type: subtask
title: Extract TestModuleIntegration class from test_mcp_server.py to test_mcp_server_lifecycle.py
description: 'Extract TestModuleIntegration class (~100 lines at test_mcp_server.py:2796-2897)
  containing 4 tests to test_mcp_server_lifecycle.py.


  What to do:

  - Locate TestModuleIntegration class at lines 2796-2897 in tests/test_mcp_server.py

  - Copy entire class to tests/test_mcp_server_lifecycle.py

  - Remove class from tests/test_mcp_server.py

  - Verify imports are present in target file


  Success criteria:

  - TestModuleIntegration exists in test_mcp_server_lifecycle.py with all 4 tests

  - TestModuleIntegration removed from test_mcp_server.py

  - No duplicate code remains'
down_dependencies:
- features.bees-m9r
parent: features.bees-3jb
created_at: '2026-02-05T16:31:01.253067'
updated_at: '2026-02-05T16:32:14.800665'
status: completed
bees_version: '1.1'
---

Extract TestModuleIntegration class (~100 lines at test_mcp_server.py:2796-2897) containing 4 tests to test_mcp_server_lifecycle.py.

What to do:
- Locate TestModuleIntegration class at lines 2796-2897 in tests/test_mcp_server.py
- Copy entire class to tests/test_mcp_server_lifecycle.py
- Remove class from tests/test_mcp_server.py
- Verify imports are present in target file

Success criteria:
- TestModuleIntegration exists in test_mcp_server_lifecycle.py with all 4 tests
- TestModuleIntegration removed from test_mcp_server.py
- No duplicate code remains
