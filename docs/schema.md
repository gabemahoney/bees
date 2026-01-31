# Ticket Schema Definition

## Overview

This document defines the schema for the markdown-based ticket system. All tickets are stored
as individual markdown files with YAML frontmatter containing metadata.

## Ticket Types

The system supports three ticket types:
- **Epic**: High-level user-facing features or goals
- **Task**: Implementation work units that belong to Epics
- **Subtask**: Atomic actions that belong to Tasks

## ID Format

**Format**: `bees-XXX` where XXX is a 3-character alphanumeric code

**Character Set**: Lowercase letters (a-z) and numbers (0-9)

**Examples**:
- `bees-250` (Epic ID)
- `bees-jty` (Task ID)
- `bees-9pw` (Subtask ID)

**Constraints**:
- IDs must be unique across all tickets
- IDs are randomly generated
- Linter validates format and catches duplicates

## Common Fields

All ticket types share these common fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique short identifier in format `bees-XXX` |
| `type` | enum | Yes | One of: `epic`, `task`, `subtask` |
| `title` | string | Yes | Short human-readable title |
| `description` | string | No | Detailed description in markdown body |
| `labels` | array[string] | No | Freeform text labels (replaces hard-coded status field) |
| `up_dependencies` | array[string] | No | IDs of tickets this ticket depends on (blocks this ticket) |
| `down_dependencies` | array[string] | No | IDs of tickets that depend on this ticket (this blocks them) |
| `parent` | string | No | ID of parent ticket (Tasks have Epic parents, Subtasks have Task parents) |
| `children` | array[string] | No | IDs of child tickets |

## Epic Ticket Schema

Epics represent high-level user-testable features or goals.

### Epic-Specific Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | enum | Yes | Must be `epic` |
| `children` | array[string] | No | IDs of child Tasks |

### Epic Example

```yaml
---
id: bees-250
type: epic
title: Core Schema and File Storage
labels:
  - in-progress
  - p0
children:
  - bees-jty
  - bees-dah
  - bees-9pw
down_dependencies: []
up_dependencies: []
parent: null
---

Implement the markdown-based ticket system with three types (Epic, Task, Subtask)
stored as individual .md files with YAML frontmatter.

## Acceptance Criteria
- Agent creates sample tickets of each type that conform to schema
- Files are written to correct directories with proper YAML frontmatter
- User can validate the markdown files are well-formed
```

## Task Ticket Schema

Tasks represent implementation work units that contribute to Epics.

### Task-Specific Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | enum | Yes | Must be `task` |
| `parent` | string | No | ID of parent Epic |
| `children` | array[string] | No | IDs of child Subtasks |

### Task Example

```yaml
---
id: bees-jty
type: task
title: Design and document ticket schema definition
labels:
  - open
  - documentation
parent: bees-250
children:
  - bees-g3s
  - bees-05h
  - bees-5bj
down_dependencies: []
up_dependencies: []
---

Define YAML frontmatter fields for Epic, Task, and Subtask types. Document field
specifications including id format, type enum, and relationship structures.
```

## Subtask Ticket Schema

Subtasks represent atomic actions that belong to Tasks.

### Subtask-Specific Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | enum | Yes | Must be `subtask` |
| `parent` | string | Yes | ID of parent Task (required for Subtasks) |
| `children` | array[string] | No | Always empty for Subtasks |

### Subtask Example

```yaml
---
id: bees-abc
type: subtask
title: Implement YAML frontmatter parser
labels:
  - open
  - backend
parent: bees-jty
children: []
down_dependencies: []
up_dependencies:
  - bees-xyz
---

Create function to parse markdown files and extract YAML frontmatter using PyYAML.
```

## Relationship Structures

### Parent-Child Relationships

**Structure**:
- `parent`: Single ID string pointing to parent ticket
- `children`: Array of ID strings pointing to child tickets

**Hierarchy**:
- Epics → Tasks (Epic.children contains Task IDs, Task.parent contains Epic ID)
- Tasks → Subtasks (Task.children contains Subtask IDs, Subtask.parent contains Task ID)

**Bidirectional Consistency**:
- If ticket A lists ticket B in its `children` array, then ticket B must list A in its `parent` field
- If ticket B lists ticket A in its `parent` field, then ticket A must include B in its `children` array
- Linter enforces this bidirectional consistency

### Dependency Relationships

**Structure**:
- `up_dependencies`: Array of ticket IDs that this ticket depends on (these tickets block this one)
- `down_dependencies`: Array of ticket IDs that depend on this ticket (this ticket blocks them)

**Semantics**:
- If ticket A is "blocked by" ticket B, then A.up_dependencies contains B
- If ticket B "blocks" ticket A, then B.down_dependencies contains A

**Bidirectional Consistency**:
- If ticket A lists ticket B in `up_dependencies`, then ticket B must list A in `down_dependencies`
- If ticket B lists ticket A in `down_dependencies`, then ticket A must list B in `up_dependencies`
- Linter enforces this bidirectional consistency

**Same-Type Restriction**:
- Epics can only depend on other Epics
- Tasks can only depend on other Tasks
- Subtasks can only depend on other Subtasks
- Cross-type dependencies are not allowed

### Cyclical Dependencies

Cyclical dependencies are **not allowed** and will be detected by the linter:
- A cannot depend on B if B depends on A (direct cycle)
- A cannot depend on B if B depends on C and C depends on A (indirect cycle)

## File Structure

Tickets are organized by type into subdirectories:

```
/tickets/
  /epics/
    epic-123.md
    epic-456.md
  /tasks/
    task-abc.md
    task-def.md
  /subtasks/
    subtask-xyz.md
    subtask-789.md
```

## Markdown Format

Each ticket file follows this structure:

```markdown
---
[YAML frontmatter with metadata fields]
---

[Markdown body with description and details]
```

**Example**:
```markdown
---
id: bees-250
type: epic
title: Core Schema and File Storage
labels: [in-progress, p0]
---

Implement the markdown-based ticket system...
```

## Labels vs Status

The system uses **freeform labels** instead of hard-coded status enums:
- Status is expressed through labels like: `open`, `in-progress`, `completed`, `blocked`
- Labels can represent any categorization: status, priority, team, feature area, etc.
- No restriction on label values - use what makes sense for your workflow
- Query system supports regex matching on labels for flexible filtering
