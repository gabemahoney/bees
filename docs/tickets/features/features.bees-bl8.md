---
id: features.bees-bl8
type: epic
title: Refactor master_plan.md into modular architecture docs
description: 'Split the monolithic master_plan.md (38k+ tokens, 68 sections) into
  focused architecture documents. Each document should be concise, avoid duplications,
  and serve as an architectural overview rather than code reference.


  **Target Structure:**


  ```

  docs/architecture/

  ├── design_principles.md    # Constraints, principles, error handling (~2k tokens)

  ├── configuration.md         # Config module, hive registry, normalization (~3k
  tokens)

  ├── storage.md              # Hive structure, ticket schema, flat storage (~3k tokens)

  ├── relationships.md        # Parent/child, dependencies, sync module (~2k tokens)

  ├── queries.md              # Query pipeline, executors, named queries (~3k tokens)

  ├── mcp_server.md           # MCP architecture, tools, integration (~2k tokens)

  ├── validation.md           # Linter, index generation, corruption (~2k tokens)

  └── testing.md              # Test strategy, fixtures, coverage (~2k tokens)

  ```


  **Content Guidelines:**

  - Focus on design decisions and rationale, not implementation

  - Reference code locations (file:line) instead of duplicating code

  - Remove verbose task-by-task histories

  - Cross-reference related docs instead of duplicating

  - Each doc should answer "why" not "how"


  **Current State:**

  - master_plan.md is 38k+ tokens with task histories, duplicate explanations, excessive
  detail

  - Mixes architectural overview with implementation history


  **Target State:**

  - 8 focused docs totaling ~19k tokens (50% reduction)

  - Clear separation of concerns

  - Easy to navigate and maintain

  - Useful for LLMs and humans understanding system design'
children:
- features.bees-a4p
- features.bees-654
- features.bees-u9o
- features.bees-oh3
- features.bees-ni4
- features.bees-dsa
- features.bees-avl
- features.bees-xdg
- features.bees-gzx
created_at: '2026-02-03T16:46:30.052016'
updated_at: '2026-02-03T16:52:21.953252'
priority: 2
status: open
bees_version: '1.1'
---

Split the monolithic master_plan.md (38k+ tokens, 68 sections) into focused architecture documents. Each document should be concise, avoid duplications, and serve as an architectural overview rather than code reference.

**Target Structure:**

```
docs/architecture/
├── design_principles.md    # Constraints, principles, error handling (~2k tokens)
├── configuration.md         # Config module, hive registry, normalization (~3k tokens)
├── storage.md              # Hive structure, ticket schema, flat storage (~3k tokens)
├── relationships.md        # Parent/child, dependencies, sync module (~2k tokens)
├── queries.md              # Query pipeline, executors, named queries (~3k tokens)
├── mcp_server.md           # MCP architecture, tools, integration (~2k tokens)
├── validation.md           # Linter, index generation, corruption (~2k tokens)
└── testing.md              # Test strategy, fixtures, coverage (~2k tokens)
```

**Content Guidelines:**
- Focus on design decisions and rationale, not implementation
- Reference code locations (file:line) instead of duplicating code
- Remove verbose task-by-task histories
- Cross-reference related docs instead of duplicating
- Each doc should answer "why" not "how"

**Current State:**
- master_plan.md is 38k+ tokens with task histories, duplicate explanations, excessive detail
- Mixes architectural overview with implementation history

**Target State:**
- 8 focused docs totaling ~19k tokens (50% reduction)
- Clear separation of concerns
- Easy to navigate and maintain
- Useful for LLMs and humans understanding system design
