---
id: features.bees-1ev
type: subtask
title: Audit test_conftest.py for assertion message format inconsistencies
description: '**Context**: Task features.bees-raw requires standardizing assertion
  messages to f-strings


  **Work**:

  - Review tests/test_conftest.py for all assertions with messages

  - Identify any using .format(), % formatting, or string concatenation

  - Document line numbers and current patterns found

  - Create list of assertions needing conversion


  **Acceptance**: Report generated listing all assertions needing conversion to f-strings'
parent: features.bees-raw
created_at: '2026-02-05T09:43:49.407150'
updated_at: '2026-02-05T10:05:58.183600'
status: completed
bees_version: '1.1'
---

**Context**: Task features.bees-raw requires standardizing assertion messages to f-strings

**Work**:
- Review tests/test_conftest.py for all assertions with messages
- Identify any using .format(), % formatting, or string concatenation
- Document line numbers and current patterns found
- Create list of assertions needing conversion

**Acceptance**: Report generated listing all assertions needing conversion to f-strings
