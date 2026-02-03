---
id: features.bees-mhy
type: subtask
title: Create src/mcp_index_ops.py with _generate_index function
description: "Context: Extract index generation logic from mcp_server.py to a dedicated\
  \ module.\n\nWhat to Create:\n- Create new file src/mcp_index_ops.py\n- Extract\
  \ _generate_index() function from src/mcp_server.py (lines 2119-2173)\n- Add necessary\
  \ imports:\n  - from typing import Dict, Any\n  - from index_generator import generate_index\n\
  \  - import logging\n- Set up logger: logger = logging.getLogger(__name__)\n\nImplementation:\n\
  - Copy function exactly as-is from mcp_server.py\n- Preserve all docstring, parameters,\
  \ and return types\n- Keep error handling intact\n\nFiles: src/mcp_index_ops.py\
  \ (new)\n\nAcceptance:\n- src/mcp_index_ops.py exists with _generate_index function\n\
  - Function signature matches original\n- All imports present and functional\n- File\
  \ is ~100-150 lines"
down_dependencies:
- features.bees-wqo
- features.bees-84q
- features.bees-fe7
parent: features.bees-zy7
created_at: '2026-02-03T17:03:13.560636'
updated_at: '2026-02-03T17:03:36.081065'
status: open
bees_version: '1.1'
---

Context: Extract index generation logic from mcp_server.py to a dedicated module.

What to Create:
- Create new file src/mcp_index_ops.py
- Extract _generate_index() function from src/mcp_server.py (lines 2119-2173)
- Add necessary imports:
  - from typing import Dict, Any
  - from index_generator import generate_index
  - import logging
- Set up logger: logger = logging.getLogger(__name__)

Implementation:
- Copy function exactly as-is from mcp_server.py
- Preserve all docstring, parameters, and return types
- Keep error handling intact

Files: src/mcp_index_ops.py (new)

Acceptance:
- src/mcp_index_ops.py exists with _generate_index function
- Function signature matches original
- All imports present and functional
- File is ~100-150 lines
