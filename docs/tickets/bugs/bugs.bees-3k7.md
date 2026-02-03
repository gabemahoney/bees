---
id: bugs.bees-3k7
type: subtask
title: Add parent= validation logic in QueryParser._validate_search_term
description: "**Context**: The _validate_search_term method in QueryParser validates\
  \ search term values. After adding 'parent=' to SEARCH_TERMS, we need to add validation\
  \ logic for parent= terms similar to how id= is validated.\n\n**What to Change**:\n\
  - In `/Users/gmahoney/projects/bees/src/query_parser.py`, in the _validate_search_term\
  \ method (starting line 160), add an elif branch for 'parent=' validation\n- Place\
  \ it after the 'id=' validation block (after line 188)\n- Validate that parent=\
  \ has a non-empty value (similar to id= validation)\n\n**Requirements**:\n```python\n\
  elif term.startswith('parent='):\n    value = term[7:]  # Skip 'parent='\n    if\
  \ not value:\n        raise QueryValidationError(\n            f\"Stage {stage_idx}:\
  \ parent= term missing value\"\n        )\n    # Optional: Add ticket ID format\
  \ validation if needed\n```\n\n**Acceptance Criteria**:\n- parent= terms with empty\
  \ values raise QueryValidationError\n- parent= terms with valid ticket IDs pass\
  \ validation\n- Error messages are clear and consistent with other term validations\n\
  \n**Reference**: Parent Task bugs.bees-yom, Blocked by bugs.bees-s3d"
up_dependencies:
- bugs.bees-s3d
down_dependencies:
- bugs.bees-9eu
parent: bugs.bees-yom
created_at: '2026-02-03T07:18:27.916224'
updated_at: '2026-02-03T07:21:42.419821'
status: completed
bees_version: '1.1'
---

**Context**: The _validate_search_term method in QueryParser validates search term values. After adding 'parent=' to SEARCH_TERMS, we need to add validation logic for parent= terms similar to how id= is validated.

**What to Change**:
- In `/Users/gmahoney/projects/bees/src/query_parser.py`, in the _validate_search_term method (starting line 160), add an elif branch for 'parent=' validation
- Place it after the 'id=' validation block (after line 188)
- Validate that parent= has a non-empty value (similar to id= validation)

**Requirements**:
```python
elif term.startswith('parent='):
    value = term[7:]  # Skip 'parent='
    if not value:
        raise QueryValidationError(
            f"Stage {stage_idx}: parent= term missing value"
        )
    # Optional: Add ticket ID format validation if needed
```

**Acceptance Criteria**:
- parent= terms with empty values raise QueryValidationError
- parent= terms with valid ticket IDs pass validation
- Error messages are clear and consistent with other term validations

**Reference**: Parent Task bugs.bees-yom, Blocked by bugs.bees-s3d
