---
id: features.bees-65m
type: subtask
title: Migrate unique test cases to appropriate test files
description: "Context: Add any unique test cases from test_writer.py to appropriate\
  \ existing test files.\n\nRequirements:\n- For each unique test case identified\
  \ in cross-reference subtask:\n  - Determine best target file (test_ticket_factory.py,\
  \ test_reader.py, or MCP tests)\n  - Adapt test code to match target file's structure\
  \ and patterns\n  - Enable the test (remove skip decorators)\n  - Ensure test uses\
  \ correct fixtures and setup\n- If no unique tests found, document that no migration\
  \ needed\n\nFiles: tests/test_ticket_factory.py, tests/test_reader.py, tests/test_mcp_*.py\n\
  \nAcceptance: All unique test cases added to appropriate files, no @pytest.skip\
  \ decorators"
up_dependencies:
- features.bees-2ao
down_dependencies:
- features.bees-6a8
parent: features.bees-nkt
created_at: '2026-02-05T09:33:47.506832'
updated_at: '2026-02-05T09:39:25.725465'
status: completed
bees_version: '1.1'
---

Context: Add any unique test cases from test_writer.py to appropriate existing test files.

Requirements:
- For each unique test case identified in cross-reference subtask:
  - Determine best target file (test_ticket_factory.py, test_reader.py, or MCP tests)
  - Adapt test code to match target file's structure and patterns
  - Enable the test (remove skip decorators)
  - Ensure test uses correct fixtures and setup
- If no unique tests found, document that no migration needed

Files: tests/test_ticket_factory.py, tests/test_reader.py, tests/test_mcp_*.py

Acceptance: All unique test cases added to appropriate files, no @pytest.skip decorators
