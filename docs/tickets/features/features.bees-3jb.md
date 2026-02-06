---
id: features.bees-3jb
type: task
title: Extract missing TestModuleIntegration class to test_mcp_server_lifecycle.py
description: 'Code review found TestModuleIntegration class (4 tests, ~100 lines at
  test_mcp_server.py:2796-2897) was not extracted to test_mcp_server_lifecycle.py
  as specified in lifecycle_tests.txt categorization.


  What Needs to Change:

  - Extract TestModuleIntegration class from test_mcp_server.py

  - Add to test_mcp_server_lifecycle.py

  - Remove from test_mcp_server.py

  - Verify all tests pass


  Success Criteria:

  - TestModuleIntegration exists in test_mcp_server_lifecycle.py

  - TestModuleIntegration removed from test_mcp_server.py

  - All tests pass

  - File size closer to ~400 line target'
labels:
- bug
up_dependencies:
- features.bees-xhi
parent: features.bees-5y8
children:
- features.bees-k1p
- features.bees-m9r
created_at: '2026-02-05T16:30:29.823387'
updated_at: '2026-02-05T16:33:01.011018'
priority: 1
status: completed
bees_version: '1.1'
---

Code review found TestModuleIntegration class (4 tests, ~100 lines at test_mcp_server.py:2796-2897) was not extracted to test_mcp_server_lifecycle.py as specified in lifecycle_tests.txt categorization.

What Needs to Change:
- Extract TestModuleIntegration class from test_mcp_server.py
- Add to test_mcp_server_lifecycle.py
- Remove from test_mcp_server.py
- Verify all tests pass

Success Criteria:
- TestModuleIntegration exists in test_mcp_server_lifecycle.py
- TestModuleIntegration removed from test_mcp_server.py
- All tests pass
- File size closer to ~400 line target
