---
id: features.bees-af3
type: subtask
title: Create src/mcp_query_ops.py with extracted query functions
description: "Context: Extract query operations from mcp_server.py into a dedicated\
  \ module. This is part of the modular refactoring to make the codebase more maintainable.\n\
  \nImplementation Steps:\n1. Create new file src/mcp_query_ops.py\n2. Move these\
  \ 3 functions from src/mcp_server.py:\n   - `_add_named_query()` (lines 1760-1816)\n\
  \   - `_execute_query()` (lines 1818-1902)\n   - `_execute_freeform_query()` (lines\
  \ 1904-1999)\n3. Add necessary imports:\n   - Query storage functions from src/query_storage.py\n\
  \   - Pipeline evaluator from src/query_pipeline.py\n   - `get_client_repo_root()`\
  \ from src/mcp_repo_utils.py\n   - FastMCP context type\n   - Standard library imports\
  \ (typing, logging, etc.)\n4. Ensure all function signatures and logic remain unchanged\n\
  5. Add module docstring explaining the module's purpose\n\nFiles Affected:\n- src/mcp_query_ops.py\
  \ (create new)\n- src/mcp_server.py (remove functions, keep tool decorators)\n\n\
  Acceptance Criteria:\n- src/mcp_query_ops.py exists with all 3 functions\n- Functions\
  \ are identical to original implementations\n- All imports are correct and minimal\n\
  - No circular dependencies\n- Module is approximately 300-400 lines\n\nParent Task:\
  \ features.bees-txe"
down_dependencies:
- features.bees-f0o
- features.bees-izl
- features.bees-wiq
parent: features.bees-txe
created_at: '2026-02-03T17:03:12.530876'
updated_at: '2026-02-03T17:03:35.769414'
status: open
bees_version: '1.1'
---

Context: Extract query operations from mcp_server.py into a dedicated module. This is part of the modular refactoring to make the codebase more maintainable.

Implementation Steps:
1. Create new file src/mcp_query_ops.py
2. Move these 3 functions from src/mcp_server.py:
   - `_add_named_query()` (lines 1760-1816)
   - `_execute_query()` (lines 1818-1902)
   - `_execute_freeform_query()` (lines 1904-1999)
3. Add necessary imports:
   - Query storage functions from src/query_storage.py
   - Pipeline evaluator from src/query_pipeline.py
   - `get_client_repo_root()` from src/mcp_repo_utils.py
   - FastMCP context type
   - Standard library imports (typing, logging, etc.)
4. Ensure all function signatures and logic remain unchanged
5. Add module docstring explaining the module's purpose

Files Affected:
- src/mcp_query_ops.py (create new)
- src/mcp_server.py (remove functions, keep tool decorators)

Acceptance Criteria:
- src/mcp_query_ops.py exists with all 3 functions
- Functions are identical to original implementations
- All imports are correct and minimal
- No circular dependencies
- Module is approximately 300-400 lines

Parent Task: features.bees-txe
