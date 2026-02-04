---
id: features.bees-dkp
type: task
title: Verify refactoring with full test suite
description: 'Context: After major refactoring, comprehensive testing is needed to
  ensure no functionality was lost and all modules integrate correctly.


  What Needs to Change:

  - Run complete pytest suite: `poetry run pytest`

  - Verify all tests pass

  - Check for any import errors or circular dependencies

  - Verify each new module is < 800 lines: `wc -l src/mcp_*.py`

  - Test MCP server startup manually if needed

  - Verify no performance regressions


  Why: This ensures the refactoring maintained all functionality and met the success
  criteria.


  Files: All src/mcp_*.py files


  Success Criteria:

  - All existing tests pass (100%)

  - No import errors or circular dependencies

  - Each module is < 800 lines

  - mcp_server.py is ~300-500 lines

  - MCP server starts and all tools work

  - Code is LLM-friendly (fits in context windows)


  Epic: features.bees-d6o'
up_dependencies:
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-k2u
- features.bees-vpi
- features.bees-ocw
- features.bees-xmo
- features.bees-9oq
- features.bees-e6p
- features.bees-0jj
- features.bees-6iz
created_at: '2026-02-03T17:02:28.301016'
updated_at: '2026-02-03T17:03:55.931416'
priority: 0
status: completed
bees_version: '1.1'
---

Context: After major refactoring, comprehensive testing is needed to ensure no functionality was lost and all modules integrate correctly.

What Needs to Change:
- Run complete pytest suite: `poetry run pytest`
- Verify all tests pass
- Check for any import errors or circular dependencies
- Verify each new module is < 800 lines: `wc -l src/mcp_*.py`
- Test MCP server startup manually if needed
- Verify no performance regressions

Why: This ensures the refactoring maintained all functionality and met the success criteria.

Files: All src/mcp_*.py files

Success Criteria:
- All existing tests pass (100%)
- No import errors or circular dependencies
- Each module is < 800 lines
- mcp_server.py is ~300-500 lines
- MCP server starts and all tools work
- Code is LLM-friendly (fits in context windows)

Epic: features.bees-d6o
