---
id: features.bees-c9p
type: epic
title: Document Test Suite Standards and Create Test Review Guide
description: "Document the cleaned-up test suite architecture and create standards\
  \ to prevent regression.\n\n## Requirements\n\n### Part 1: Update testing.md\n-\
  \ Review all completed Test Cleanup epics (5va, utd, y6w, 74p, 1u8, 5y8, w0c)\n\
  - Update docs/architecture/testing.md to reflect:\n  - New shared fixture architecture\
  \ (bees_repo, single_hive, multi_hive, hive_with_tickets)\n  - Test file organization\
  \ (factory vs MCP integration)\n  - Coverage standards for simple functions\n  -\
  \ Mock patching patterns\n  - File size limits and organization principles\n- Remove\
  \ outdated information\n- Keep concise (target: 2k tokens or less)\n\n### Part 2:\
  \ Create Test Review Guide\n- Create docs/test_review_guide.md as a prompt for Test\
  \ Review agents\n- Guide should be SHORT and CONCISE (1 page max)\n- Provide clear\
  \ checklist to prevent:\n  1. **Fixture duplication** - All shared setup must use\
  \ conftest.py fixtures\n  2. **Overlapping coverage** - No duplicate test cases\
  \ across files\n  3. **Monolithic files** - Max file size limits (1,600 lines)\n\
  \  4. **Over-testing** - Simple functions get minimal essential coverage only\n\
  \  5. **Dead code** - No skipped test files, no commented-out tests\n  6. **Fragile\
  \ mocking** - Patch at source, document all mock locations\n- Each item should have:\n\
  \  - **What to check** - Specific grep/find commands or file analysis\n  - **Red\
  \ flags** - Patterns that indicate problems\n  - **Fix** - What to do when problems\
  \ are found\n\n## Acceptance Criteria\n\n### testing.md\n- User reads docs/architecture/testing.md\
  \ - understands test suite in under 5 minutes\n- Document is ≤2k tokens\n- Accurately\
  \ reflects current test architecture post-cleanup\n- No references to deleted test\
  \ files or old patterns\n\n### test_review_guide.md  \n- User reads docs/test_review_guide.md\
  \ - has clear checklist in under 2 minutes\n- Document is ≤500 tokens (1 page)\n\
  - Agent can use this as a prompt to review test changes\n- Each check has concrete\
  \ commands/patterns to look for\n- Prevents all 6 problem categories from Test Cleanup\
  \ epics\n\n## Example Review Check Format\n\n```markdown\n## 1. Fixture Duplication\n\
  \n**Check:** Search for local fixture definitions\n```bash\nrg \"@pytest.fixture\"\
  \ tests/ --type py | grep -v conftest.py\n```\n\n**Red Flags:**\n- Multiple files\
  \ defining setup_tickets_dir, temp_hive_setup, etc.\n- Fixture code duplicated across\
  \ 3+ files\n\n**Fix:** Extract to conftest.py with tiered fixture design\n```\n\n\
  Source: Test Cleanup Epics (features.bees-5va, features.bees-utd, features.bees-y6w,\
  \ features.bees-74p, features.bees-1u8, features.bees-5y8, features.bees-w0c)"
labels:
- not-started
up_dependencies:
- features.bees-5va
- features.bees-utd
- features.bees-y6w
- features.bees-74p
- features.bees-1u8
- features.bees-5y8
- features.bees-w0c
created_at: '2026-02-05T10:35:12.379006'
updated_at: '2026-02-05T10:35:18.544571'
priority: 2
status: open
bees_version: '1.1'
---

Document the cleaned-up test suite architecture and create standards to prevent regression.

## Requirements

### Part 1: Update testing.md
- Review all completed Test Cleanup epics (5va, utd, y6w, 74p, 1u8, 5y8, w0c)
- Update docs/architecture/testing.md to reflect:
  - New shared fixture architecture (bees_repo, single_hive, multi_hive, hive_with_tickets)
  - Test file organization (factory vs MCP integration)
  - Coverage standards for simple functions
  - Mock patching patterns
  - File size limits and organization principles
- Remove outdated information
- Keep concise (target: 2k tokens or less)

### Part 2: Create Test Review Guide
- Create docs/test_review_guide.md as a prompt for Test Review agents
- Guide should be SHORT and CONCISE (1 page max)
- Provide clear checklist to prevent:
  1. **Fixture duplication** - All shared setup must use conftest.py fixtures
  2. **Overlapping coverage** - No duplicate test cases across files
  3. **Monolithic files** - Max file size limits (1,600 lines)
  4. **Over-testing** - Simple functions get minimal essential coverage only
  5. **Dead code** - No skipped test files, no commented-out tests
  6. **Fragile mocking** - Patch at source, document all mock locations
- Each item should have:
  - **What to check** - Specific grep/find commands or file analysis
  - **Red flags** - Patterns that indicate problems
  - **Fix** - What to do when problems are found

## Acceptance Criteria

### testing.md
- User reads docs/architecture/testing.md - understands test suite in under 5 minutes
- Document is ≤2k tokens
- Accurately reflects current test architecture post-cleanup
- No references to deleted test files or old patterns

### test_review_guide.md  
- User reads docs/test_review_guide.md - has clear checklist in under 2 minutes
- Document is ≤500 tokens (1 page)
- Agent can use this as a prompt to review test changes
- Each check has concrete commands/patterns to look for
- Prevents all 6 problem categories from Test Cleanup epics

## Example Review Check Format

```markdown
## 1. Fixture Duplication

**Check:** Search for local fixture definitions
```bash
rg "@pytest.fixture" tests/ --type py | grep -v conftest.py
```

**Red Flags:**
- Multiple files defining setup_tickets_dir, temp_hive_setup, etc.
- Fixture code duplicated across 3+ files

**Fix:** Extract to conftest.py with tiered fixture design
```

Source: Test Cleanup Epics (features.bees-5va, features.bees-utd, features.bees-y6w, features.bees-74p, features.bees-1u8, features.bees-5y8, features.bees-w0c)
