---
id: features.bees-u2o
type: subtask
title: Remove Repository Root Detection section from README.md
description: "**Context**: README.md lines 21-27 contain a \"Repository Root Detection\"\
  \ section that documents internal implementation details of `src/mcp_repo_utils.py`.\
  \ This violates README best practices which state that READMEs should be user-facing\
  \ only, focused on installation and usage.\n\n**What to do**:\n- Delete lines 21-27\
  \ from README.md (the entire \"### Repository Root Detection\" section)\n- Keep\
  \ the \"### Testing\" section (lines 25-27) which provides useful context about\
  \ test coverage\n- Verify the removal doesn't break any markdown structure or formatting\n\
  \n**Files**: \n- `/Users/gmahoney/projects/bees/README.md`\n\n**Acceptance criteria**:\n\
  - Lines 21-27 removed from README.md\n- \"### Testing\" section remains intact\n\
  - No broken markdown formatting\n- README flows naturally from \"MCP Client Requirements\"\
  \ section to \"Testing\" section"
parent: features.bees-c4r
created_at: '2026-02-03T19:26:50.788304'
updated_at: '2026-02-03T19:28:04.774074'
status: completed
bees_version: '1.1'
---

**Context**: README.md lines 21-27 contain a "Repository Root Detection" section that documents internal implementation details of `src/mcp_repo_utils.py`. This violates README best practices which state that READMEs should be user-facing only, focused on installation and usage.

**What to do**:
- Delete lines 21-27 from README.md (the entire "### Repository Root Detection" section)
- Keep the "### Testing" section (lines 25-27) which provides useful context about test coverage
- Verify the removal doesn't break any markdown structure or formatting

**Files**: 
- `/Users/gmahoney/projects/bees/README.md`

**Acceptance criteria**:
- Lines 21-27 removed from README.md
- "### Testing" section remains intact
- No broken markdown formatting
- README flows naturally from "MCP Client Requirements" section to "Testing" section
