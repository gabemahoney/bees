---
id: bugs.bees-jru
type: subtask
title: Update README.md with tool naming test documentation
description: 'Context: New integration test verifies MCP tool naming pattern compliance.


  What to Update:

  - File: README.md

  - Section: Testing (or create if doesn''t exist)

  - Add documentation for test_mcp_tool_naming.py

  - Explain purpose: verify tools use mcp_bees_* prefix pattern

  - Note: This test prevents regression to incorrect naming patterns


  Content Guidelines:

  - Brief description of tool naming conventions

  - Why this test matters (MCP naming standards compliance)

  - Reference to MCP naming conventions if applicable


  Success Criteria:

  - README.md updated with test documentation

  - Clear explanation of tool naming verification

  - Follows existing README documentation style


  References:

  - Parent Task: bugs.bees-hl0

  - Implementation Subtask: bugs.bees-763'
parent: bugs.bees-hl0
up_dependencies:
- bugs.bees-763
status: open
created_at: '2026-02-03T07:22:10.914205'
updated_at: '2026-02-03T07:22:10.914214'
bees_version: '1.1'
---

Context: New integration test verifies MCP tool naming pattern compliance.

What to Update:
- File: README.md
- Section: Testing (or create if doesn't exist)
- Add documentation for test_mcp_tool_naming.py
- Explain purpose: verify tools use mcp_bees_* prefix pattern
- Note: This test prevents regression to incorrect naming patterns

Content Guidelines:
- Brief description of tool naming conventions
- Why this test matters (MCP naming standards compliance)
- Reference to MCP naming conventions if applicable

Success Criteria:
- README.md updated with test documentation
- Clear explanation of tool naming verification
- Follows existing README documentation style

References:
- Parent Task: bugs.bees-hl0
- Implementation Subtask: bugs.bees-763
