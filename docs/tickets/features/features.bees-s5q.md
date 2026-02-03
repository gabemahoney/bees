---
id: features.bees-s5q
type: subtask
title: Update README.md with refactored architecture documentation
description: "Context: The mcp_server.py refactoring significantly changes the codebase\
  \ architecture. README should document the new modular structure.\n\nWhat to Add:\n\
  - Update architecture section to explain the new module breakdown\n- Document that\
  \ mcp_server.py is now a thin orchestration layer\n- List the 9 extracted modules\
  \ and their responsibilities:\n  - mcp_id_utils: Ticket ID parsing\n  - mcp_repo_utils:\
  \ Repository root detection\n  - mcp_hive_utils: Hive validation and discovery\n\
  \  - mcp_relationships: Bidirectional relationship sync\n  - mcp_ticket_ops: Ticket\
  \ CRUD operations\n  - mcp_hive_ops: Hive lifecycle operations\n  - mcp_query_ops:\
  \ Query execution\n  - mcp_index_ops: Index generation\n  - mcp_help: Help documentation\n\
  - Note that each module is < 800 lines for LLM context compatibility\n\nFiles: README.md\n\
  \nAcceptance: README documents the new modular architecture with clear explanation\
  \ of module responsibilities."
parent: features.bees-4u5
up_dependencies:
- features.bees-b1s
status: open
created_at: '2026-02-03T17:03:37.778468'
updated_at: '2026-02-03T17:03:37.778471'
bees_version: '1.1'
---

Context: The mcp_server.py refactoring significantly changes the codebase architecture. README should document the new modular structure.

What to Add:
- Update architecture section to explain the new module breakdown
- Document that mcp_server.py is now a thin orchestration layer
- List the 9 extracted modules and their responsibilities:
  - mcp_id_utils: Ticket ID parsing
  - mcp_repo_utils: Repository root detection
  - mcp_hive_utils: Hive validation and discovery
  - mcp_relationships: Bidirectional relationship sync
  - mcp_ticket_ops: Ticket CRUD operations
  - mcp_hive_ops: Hive lifecycle operations
  - mcp_query_ops: Query execution
  - mcp_index_ops: Index generation
  - mcp_help: Help documentation
- Note that each module is < 800 lines for LLM context compatibility

Files: README.md

Acceptance: README documents the new modular architecture with clear explanation of module responsibilities.
