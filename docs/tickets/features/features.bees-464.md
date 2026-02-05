---
id: features.bees-464
type: subtask
title: Add ticket_id format validation to write_ticket_file()
description: 'Add input validation to write_ticket_file() in src/writer.py:67 to prevent
  path traversal attacks.


  **Context**: Security vulnerability - write_ticket_file() accepts ticket_id without
  validating format, allowing potential path traversal.


  **Requirements**:

  - Import validate_id_format from src/validator.py

  - Add validation check at start of write_ticket_file() before calling get_ticket_path()

  - Raise ValueError with descriptive message if ticket_id format is invalid

  - Ensure validation happens before any filesystem operations


  **Files to modify**:

  - src/writer.py (line 67-142)


  **Acceptance criteria**:

  - write_ticket_file() calls validate_id_format(ticket_id) before get_ticket_path()

  - Invalid ticket_id raises ValueError with message like "Invalid ticket ID format:
  {ticket_id}"

  - Valid ticket_ids continue to work as before'
down_dependencies:
- features.bees-5ry
- features.bees-a3l
- features.bees-5k8
parent: features.bees-y9a
created_at: '2026-02-05T09:43:33.012119'
updated_at: '2026-02-05T09:44:59.738337'
status: completed
bees_version: '1.1'
---

Add input validation to write_ticket_file() in src/writer.py:67 to prevent path traversal attacks.

**Context**: Security vulnerability - write_ticket_file() accepts ticket_id without validating format, allowing potential path traversal.

**Requirements**:
- Import validate_id_format from src/validator.py
- Add validation check at start of write_ticket_file() before calling get_ticket_path()
- Raise ValueError with descriptive message if ticket_id format is invalid
- Ensure validation happens before any filesystem operations

**Files to modify**:
- src/writer.py (line 67-142)

**Acceptance criteria**:
- write_ticket_file() calls validate_id_format(ticket_id) before get_ticket_path()
- Invalid ticket_id raises ValueError with message like "Invalid ticket ID format: {ticket_id}"
- Valid ticket_ids continue to work as before
