---
id: features.bees-z4o
type: subtask
title: Update supported/unsupported clients list for fallback availability
description: '**Context**: The supported clients list currently excludes clients without
  roots protocol support. With fallback support, these clients can now use bees with
  explicit repo_root parameter.


  **Requirements**:

  - Review current supported/unsupported clients list in README.md

  - Update list to reflect that previously unsupported clients can now work via fallback

  - Add notes about which approach each client uses (roots vs fallback)

  - Keep messaging clear about which approach is recommended


  **Files**: README.md


  **Acceptance**: Clients list accurately reflects current support status with fallback,
  users understand their options.'
parent: features.bees-uen
created_at: '2026-02-03T06:41:33.012320'
updated_at: '2026-02-03T13:11:39.470365'
status: completed
bees_version: '1.1'
---

**Context**: The supported clients list currently excludes clients without roots protocol support. With fallback support, these clients can now use bees with explicit repo_root parameter.

**Requirements**:
- Review current supported/unsupported clients list in README.md
- Update list to reflect that previously unsupported clients can now work via fallback
- Add notes about which approach each client uses (roots vs fallback)
- Keep messaging clear about which approach is recommended

**Files**: README.md

**Acceptance**: Clients list accurately reflects current support status with fallback, users understand their options.
