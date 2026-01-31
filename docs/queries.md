# Query System Reference Guide

Complete reference for the Bees multi-stage query pipeline system.

## Table of Contents

- [Overview](#overview)
- [Query Structure](#query-structure)
- [Search Terms](#search-terms)
- [Graph Terms](#graph-terms)
- [Stage Evaluation](#stage-evaluation)
- [Regex Patterns](#regex-patterns)
- [Named Queries](#named-queries)
- [Parameterized Queries](#parameterized-queries)
- [Performance Considerations](#performance-considerations)
- [Advanced Patterns](#advanced-patterns)

## Overview

The Bees query system provides a declarative, pipeline-based approach to filtering
and traversing ticket data. Queries are expressed as YAML lists of stages, where
each stage filters or traverses the result set from the previous stage.

**Key Design Principles**:

- **Declarative**: Describe what you want, not how to get it
- **Composable**: Chain simple stages to build complex queries
- **Efficient**: All tickets loaded once, stages execute in-memory
- **Type-safe**: Strict separation of search and graph operations

## Query Structure

### Basic Syntax

A query is a YAML list where each element is a stage:

```yaml
- ['type=epic']           # Stage 1
- ['children']            # Stage 2
- ['label~open']          # Stage 3
```

### Stages

Each stage is a list of terms:

```yaml
- ['type=task', 'label~beta', 'title~API']  # 3 terms in 1 stage
```

### Terms

Terms are strings following specific formats:

**Search terms** (attribute filtering):
```
type=VALUE
id=VALUE
title~REGEX
label~REGEX
```

**Graph terms** (relationship traversal):
```
parent
children
up_dependencies
down_dependencies
```

### Pipeline Semantics

1. **Sequential execution**: Stages run in order (stage 1, then 2, then 3, etc.)
2. **Result passing**: Output of stage N becomes input to stage N+1
3. **Deduplication**: Ticket IDs deduplicated after each stage
4. **Short-circuit**: Empty result stops pipeline immediately
5. **Stage purity**: Each stage is ONLY search OR ONLY graph, never mixed

## Search Terms

Search terms filter tickets by matching attributes using AND logic within a stage.

### type= (Exact Match)

Filter by ticket type: `epic`, `task`, or `subtask`.

**Syntax**: `type=VALUE`

**Examples**:
```yaml
- ['type=epic']               # Only epics
- ['type=task']               # Only tasks
- ['type=subtask']            # Only subtasks
- ['type=task', 'type=epic']  # Invalid: conflicting types (returns empty)
```

**Validation**: Value must be exactly `epic`, `task`, or `subtask` (case-
sensitive).

**Use case**: Start queries by filtering to specific ticket type, then add more
filters or traverse relationships.

### id= (Exact Match)

Filter by exact ticket ID.

**Syntax**: `id=VALUE`

**Examples**:
```yaml
- ['id=bees-250']                        # Single ticket by ID
- ['id=bees-250', 'id=bees-xyz']         # Invalid: conflicting IDs
```

**Validation**: Value should be valid ticket ID format (e.g., `bees-abc`).

**Use case**: Find specific ticket or verify ticket existence. Often used as
starting point for relationship traversal.

```yaml
# Find parent of specific ticket
- ['id=bees-tk1']
- ['parent']
```

### title~ (Regex Match)

Filter by title using regular expression pattern matching.

**Syntax**: `title~REGEX`

**Examples**:
```yaml
# Case-insensitive substring match
- ['title~(?i)authentication']

# Starts with "Task:"
- ['title~^Task:']

# Contains "API" or "REST"
- ['title~(API|REST)']

# Contains "API" but not "deprecated"
- ['title~(?=.*API)(?!.*deprecated).*']
```

**Matching behavior**:
- Case-sensitive by default (use `(?i)` flag for case-insensitive)
- Matches anywhere in title unless anchored with `^` (start) or `$` (end)
- Full Python regex syntax supported

**Common patterns**:
```yaml
- ['title~(?i)api']           # Case-insensitive "api" anywhere
- ['title~^Epic:']             # Starts with "Epic:"
- ['title~system$']            # Ends with "system"
- ['title~\[WIP\]']            # Contains "[WIP]" (brackets escaped)
```

**Use case**: Search tickets by content in title field, especially when combined
with type filters.

### label~ (Regex Match)

Filter by labels using regular expression pattern matching. Matches if ANY label
matches the pattern.

**Syntax**: `label~REGEX`

**Examples**:
```yaml
# Matches tickets with "beta" in any label
- ['label~beta']

# OR pattern: matches beta OR alpha OR preview
- ['label~(beta|alpha|preview)']

# Priority labels p0-p4
- ['label~p[0-4]']

# Negation: NOT containing "closed"
- ['label~^(?!.*closed).*']

# Status labels (case-insensitive)
- ['label~(?i)(open|in progress|blocked)']
```

**Matching behavior**:
- Matches against each label in ticket's label array
- Returns ticket if ANY label matches pattern
- Case-sensitive by default (use `(?i)` flag)
- Empty label array never matches

**Multiple label filters (AND logic)**:
```yaml
# Must have BOTH beta AND open labels
- ['label~beta', 'label~open']

# Must have priority p0-p2 AND NOT closed
- ['label~p[0-2]', 'label~^(?!.*closed).*']
```

**Use case**: Most flexible search term. Use for filtering by status, priority,
tags, or any freeform categorization.

### Combining Search Terms

Multiple search terms in a stage use AND logic - ticket must match ALL terms:

```yaml
# Type AND label AND title
- ['type=task', 'label~backend', 'title~API']
```

This finds tasks that:
1. Are type=task AND
2. Have "backend" in a label AND
3. Have "API" in title

**Filter order optimization**: Put most restrictive filters first to short-circuit
faster:

```yaml
# Good: Filter to specific ID first (most restrictive)
- ['id=bees-250', 'label~open']

# Less efficient: Filter all open items, then down to one ID
- ['label~open', 'id=bees-250']
```

## Graph Terms

Graph terms traverse ticket relationships from the current result set.

### children

Get child tickets (Epic→Tasks, Task→Subtasks).

**Syntax**: `children`

**Example**:
```yaml
# Find all tasks under beta epics
- ['type=epic', 'label~beta']
- ['children']
```

**Behavior**:
- Looks up `children` field in each input ticket
- Returns set of all child ticket IDs
- Automatically deduplicates (multiple tickets can share children)
- Returns empty set if no children exist

**Use case**: Navigate down hierarchy to find subtasks/tasks under parent items.

### parent

Get parent ticket (Task→Epic, Subtask→Task).

**Syntax**: `parent`

**Example**:
```yaml
# Find epics that have high-priority tasks
- ['type=task', 'label~p0']
- ['parent']
```

**Behavior**:
- Looks up `parent` field in each input ticket
- Returns set of parent ticket IDs
- Returns empty set if parent field is None/empty
- Multiple children can have same parent (automatic deduplication)

**Use case**: Navigate up hierarchy to find parent epics/tasks.

### up_dependencies

Get blocking tickets (tickets this one depends on).

**Syntax**: `up_dependencies`

**Example**:
```yaml
# Find what's blocking open tasks
- ['type=task', 'label~open']
- ['up_dependencies']
```

**Behavior**:
- Looks up `up_dependencies` field in each input ticket
- Returns set of all blocking ticket IDs
- Returns empty set if no dependencies
- Use to find blockers/prerequisites

**Use case**: Identify bottlenecks by finding what blocks open work items.

### down_dependencies

Get blocked tickets (tickets that depend on this one).

**Syntax**: `down_dependencies`

**Example**:
```yaml
# Find what would be unblocked if we complete API tasks
- ['type=task', 'label~api']
- ['down_dependencies']
```

**Behavior**:
- Looks up `down_dependencies` field in each input ticket
- Returns set of all dependent ticket IDs
- Returns empty set if nothing depends on this ticket
- Use to find impact of completing a ticket

**Use case**: Assess impact by finding what work would be unblocked.

### Chaining Graph Terms

Chain multiple graph stages to traverse multi-hop relationships:

```yaml
# Find grandchildren of epics (Epic → Task → Subtask)
- ['type=epic']
- ['children']      # Get tasks
- ['children']      # Get subtasks

# Find transitive dependencies (what blocks what blocks me)
- ['id=bees-tk1']
- ['up_dependencies']    # Direct blockers
- ['up_dependencies']    # Blockers of blockers
```

### Combining Graph and Search

Alternate graph and search stages to filter at each level:

```yaml
# Find open subtasks of beta tasks
- ['type=task', 'label~beta']    # Search: Find beta tasks
- ['children']                    # Graph: Get subtasks
- ['label~open']                  # Search: Filter to open items

# Find parents of blocked work
- ['label~blocked']               # Search: Find blocked items
- ['parent']                      # Graph: Get parents
- ['type=epic']                   # Search: Filter to epics only
```

## Stage Evaluation

### Execution Order

Stages execute sequentially left-to-right (top-to-bottom in YAML):

```yaml
- ['type=epic']          # Stage 1: Start with all tickets, filter to epics
- ['label~beta']         # Stage 2: Start with epics, filter to beta
- ['children']           # Stage 3: Start with beta epics, get children
```

### Result Passing

Each stage receives the ticket IDs output by the previous stage:

```
All Tickets    → Stage 1 → {IDs}  → Stage 2 → {IDs}  → Stage 3 → {IDs} (final result)
{all IDs}                 filter           filter          traverse
```

**Example trace**:
```yaml
- ['type=epic']          # Input: all tickets → Output: {bees-ep1, bees-ep2}
- ['label~beta']         # Input: {ep1, ep2} → Output: {bees-ep1}
- ['children']           # Input: {ep1} → Output: {bees-tk1, bees-tk2}
```

### Deduplication

Results deduplicated after each stage using set operations:

```yaml
# Two tasks have same parent epic
- ['type=task', 'label~backend']  # Returns: {bees-tk1, bees-tk2}
- ['parent']                       # Both have parent bees-ep1
                                   # Raw: [bees-ep1, bees-ep1]
                                   # Deduplicated: {bees-ep1}
```

This prevents duplicate ticket IDs in results.

### Short-Circuit Evaluation

Pipeline stops immediately if any stage returns empty set:

```yaml
- ['type=epic']          # Returns: {bees-ep1, bees-ep2}
- ['label~closed']       # Returns: {} (no closed epics)
- ['children']           # NOT EXECUTED - pipeline terminated
- ['label~open']         # NOT EXECUTED
```

**Result**: Empty set `{}`

This optimization avoids unnecessary stage execution.

### Stage Type Detection

Pipeline automatically detects stage type by inspecting terms:

```yaml
- ['type=epic', 'label~beta']    # Search stage (has search terms)
- ['children']                    # Graph stage (has graph term)
- ['type=task']                   # Search stage
```

**Validation**: Raises error if stage mixes search and graph terms:

```yaml
- ['type=epic', 'children']      # ERROR: Mixed stage types
```

## Regex Patterns

Full Python regex syntax supported in `title~` and `label~` terms.

### Basic Patterns

**Literal match**:
```yaml
- ['label~beta']         # Matches label containing "beta"
- ['title~API']          # Matches title containing "API"
```

**Case insensitive**:
```yaml
- ['label~(?i)beta']     # Matches: beta, Beta, BETA, BeTa
```

**Anchors**:
```yaml
- ['title~^Task:']       # Starts with "Task:"
- ['title~complete$']    # Ends with "complete"
- ['title~^Task: .*$']   # Entire title matches "Task: <anything>"
```

### Character Classes

**Ranges**:
```yaml
- ['label~p[0-4]']       # Matches: p0, p1, p2, p3, p4
- ['label~[a-z]+']       # One or more lowercase letters
- ['label~[A-Z]{2,}']    # Two or more uppercase letters
```

**Character sets**:
```yaml
- ['label~[aeiou]']      # Contains any vowel
- ['label~[^0-9]']       # Contains non-digit (^ negates inside [])
```

### Quantifiers

```yaml
- ['title~API.*']        # "API" followed by zero or more chars
- ['title~API.+']        # "API" followed by one or more chars
- ['title~API.?']        # "API" followed by zero or one char
- ['title~API.{3}']      # "API" followed by exactly 3 chars
- ['title~API.{2,5}']    # "API" followed by 2 to 5 chars
```

### Alternation (OR)

```yaml
- ['label~(beta|alpha|preview)']       # Matches any of these
- ['title~(API|REST|GraphQL)']         # Technology keywords
- ['label~(open|in progress)']         # Status values
```

**Without grouping** (less common):
```yaml
- ['label~beta|alpha']   # Matches "beta" OR entire label is "alpha"
                          # Usually want grouping instead: (beta|alpha)
```

### Lookahead Assertions

**Positive lookahead** (`(?=...)`): Assert pattern exists ahead without consuming:
```yaml
# Contains "API" AND "auth"
- ['title~(?=.*API)(?=.*auth).*']
```

**Negative lookahead** (`(?!...)`): Assert pattern doesn't exist ahead:
```yaml
# NOT containing "closed"
- ['label~^(?!.*closed).*']

# NOT containing "preview"
- ['label~^(?!.*preview).*']

# Contains "task" but NOT "deprecated"
- ['title~(?=.*task)(?!.*deprecated).*']
```

### Escaping Special Characters

Escape regex metacharacters with backslash:

```yaml
# Metacharacters: . ^ $ * + ? { } [ ] \ | ( )
- ['title~\[WIP\]']              # Literal "[WIP]"
- ['label~version-1\.0']         # Literal "version-1.0"
- ['title~\(draft\)']            # Literal "(draft)"
```

### Word Boundaries

```yaml
- ['title~\bAPI\b']      # Word "API" (not "APIC" or "myAPI")
- ['label~\bopen\b']     # Word "open" (not "opened" or "reopen")
```

### Common Regex Patterns

**Priority labels**:
```yaml
- ['label~p[0-4]']               # p0, p1, p2, p3, p4
- ['label~priority-(high|medium|low)']
```

**Status labels**:
```yaml
- ['label~(?i)(open|in progress|blocked|closed)']
```

**Version numbers**:
```yaml
- ['label~v[0-9]+\.[0-9]+\.[0-9]+']   # v1.2.3
```

**Dates** (YYYY-MM-DD):
```yaml
- ['label~\d{4}-\d{2}-\d{2}']
```

**Feature flags**:
```yaml
- ['label~(feature|bugfix|hotfix)-.*']
```

**Exclusion patterns**:
```yaml
- ['label~^(?!.*(closed|archived|deprecated)).*']
```

## Named Queries

Named queries let you save and reuse query definitions.

### Storage

Named queries are stored in `.bees/queries.yaml`:

```yaml
# .bees/queries.yaml
---
open_beta_items:
  - ['type=epic', 'label~(?i)(beta|preview)']
  - ['children']
  - ['label~(?i)(open|in progress)']

high_priority:
  - ['label~p[0-2]']

blocked_tasks:
  - ['type=task', 'label~open']
  - ['up_dependencies']
```

### Registering Queries

**Via MCP** (programmatic):
```python
from mcp_tools import add_named_query

query_yaml = """
- ['type=task', 'label~backend']
- ['parent']
"""
add_named_query(name="backend_task_parents", query_yaml=query_yaml)
```

**Via manual editing**:
1. Open `.bees/queries.yaml`
2. Add query using YAML syntax
3. Save file
4. Restart MCP server (or it auto-reloads)

### Executing Named Queries

```python
from mcp_tools import execute_query

result = execute_query("open_beta_items")
# Returns: {"status": "success", "result_count": 5, "ticket_ids": [...]}
```

### Query Naming Conventions

**Recommended naming**:
- Use snake_case: `open_beta_items`, `high_priority_tasks`
- Descriptive: Name describes what query returns
- Consistent: Use common prefixes/suffixes (`*_items`, `find_*`, `get_*`)

**Avoid**:
- Special characters beyond underscore
- Very long names (>50 chars)
- Generic names like "query1", "test", "temp"

### Query Listing

List all registered queries:

```python
from src.query_storage import list_queries

queries = list_queries()
print(f"Available: {', '.join(queries)}")
```

## Parameterized Queries

Parameterized queries use placeholders for dynamic values at execution time.

### Placeholder Syntax

Use `{param_name}` for placeholders:

```yaml
# Query template
parameterized_filter:
  - ['type={ticket_type}', 'label~{label_pattern}']
```

### Registering Parameterized Queries

Set `validate=False` to skip validation (placeholders won't validate):

```python
query_yaml = """
- ['type={ticket_type}', 'label~{label_pattern}']
"""
add_named_query(
    name="type_label_filter",
    query_yaml=query_yaml,
    validate=False  # Required for parameterized queries
)
```

### Executing with Parameters

Pass parameter values as JSON string:

```python
params = '{"ticket_type": "task", "label_pattern": "beta"}'
result = execute_query("type_label_filter", params=params)
# Executes: [['type=task', 'label~beta']]
```

### Parameter Substitution

Parameters are substituted before query execution:

**Template**:
```yaml
- ['type={type}', 'label~{label}']
- ['{relationship}']
```

**Parameters**:
```json
{
  "type": "epic",
  "label": "beta",
  "relationship": "children"
}
```

**Executed query**:
```yaml
- ['type=epic', 'label~beta']
- ['children']
```

### Use Cases

**Reusable search templates**:
```yaml
# Template
search_by_type_and_label:
  - ['type={type}', 'label~{pattern}']

# Execute with different parameters
execute_query("search_by_type_and_label",
              params='{"type": "task", "pattern": "backend"}')
execute_query("search_by_type_and_label",
              params='{"type": "epic", "pattern": "feature-.*"}')
```

**Dynamic relationship traversal**:
```yaml
# Template
traverse_from_id:
  - ['id={ticket_id}']
  - ['{direction}']

# Go up
execute_query("traverse_from_id",
              params='{"ticket_id": "bees-tk1", "direction": "parent"}')

# Go down
execute_query("traverse_from_id",
              params='{"ticket_id": "bees-ep1", "direction": "children"}')
```

### Parameter Validation

Parameters validated at execution time:

```python
# Error: Missing required parameter
execute_query("type_label_filter", params='{}')
# ValueError: Missing required parameter: ticket_type

# Error: Invalid JSON
execute_query("type_label_filter", params='not json')
# ValueError: Invalid JSON in params: ...
```

## Performance Considerations

### Loading Strategy

**Initial load**:
- All tickets loaded from `.beads/issues.jsonl` once during pipeline initialization
- Time: O(n) where n = total tickets
- Memory: O(n) - all ticket data in memory

**Query execution**:
- No disk I/O during query execution
- All filtering/traversal uses in-memory data
- Time: O(s * m) where s = stages, m = avg tickets per stage

### Query Optimization

**Filter early**: Put most restrictive filters in early stages:

```yaml
# Good: Filter to one ticket first
- ['id=bees-tk1']
- ['up_dependencies']
- ['label~open']

# Bad: Filter all open tickets first, then to one ticket
- ['label~open']
- ['id=bees-tk1']
- ['up_dependencies']
```

**Minimize stages**: Combine filters in same stage when possible:

```yaml
# Better: One search stage
- ['type=task', 'label~beta', 'label~open']

# Worse: Three stages
- ['type=task']
- ['label~beta']
- ['label~open']
```

**Avoid redundant traversals**: Don't traverse same relationship twice:

```yaml
# Redundant
- ['children']
- ['children']  # Going down twice

# If you need grandchildren, be explicit
- ['type=epic']
- ['children']  # Epic -> Task
- ['children']  # Task -> Subtask
```

### Short-Circuit Benefits

Queries short-circuit on empty results, so failing fast is efficient:

```yaml
# If no closed epics exist, stops after stage 2
- ['type=epic']
- ['label~closed']  # Returns empty
- ['children']      # NOT executed
```

### Regex Performance

**Simple patterns are faster**:
```yaml
- ['label~beta']           # Fast: simple substring
- ['label~p[0-4]']         # Fast: character class
```

**Complex patterns slower**:
```yaml
- ['label~(?=.*a)(?=.*b)(?=.*c).*']  # Slower: multiple lookaheads
```

**Precompile patterns**: Parser compiles regex once during validation, reused
during execution.

### Caching

**Pipeline instance reuse**: Create one pipeline, execute multiple queries:

```python
pipeline = PipelineEvaluator()  # Loads tickets once

# Reuse for multiple queries
result1 = pipeline.execute_query(query1)
result2 = pipeline.execute_query(query2)
result3 = pipeline.execute_query(query3)
# Tickets loaded once, used 3 times
```

**Named query execution**: MCP server keeps pipeline instance alive, reuses for
all named query executions.

## Advanced Patterns

### Multi-Level Filtering

Filter at each level of hierarchy:

```yaml
# Find open subtasks of beta tasks under feature epics
- ['type=epic', 'label~feature-.*']    # Feature epics
- ['children']                          # Their tasks
- ['label~beta']                        # Beta tasks only
- ['children']                          # Their subtasks
- ['label~open']                        # Open subtasks only
```

### Bidirectional Traversal

Navigate up then down:

```yaml
# Find sibling tasks (same parent)
- ['id=bees-tk1']      # Start with one task
- ['parent']           # Go up to epic
- ['children']         # Go down to all tasks
# Result includes original task + its siblings
```

### Dependency Chains

Find transitive dependencies:

```yaml
# What blocks what blocks me? (2-hop dependencies)
- ['id=bees-tk1']
- ['up_dependencies']    # Direct blockers
- ['up_dependencies']    # Blockers of blockers
```

### Impact Analysis

Assess change impact:

```yaml
# What would completing this epic unblock?
- ['id=bees-ep1']
- ['down_dependencies']  # Immediate dependents
- ['down_dependencies']  # Transitive dependents
```

### Set Operations via Regex

**Union (OR)**: Use regex alternation:
```yaml
- ['label~(beta|alpha|preview)']   # beta OR alpha OR preview
```

**Intersection (AND)**: Use multiple terms:
```yaml
- ['label~beta', 'label~open']     # beta AND open
```

**Difference (NOT)**: Use negative lookahead:
```yaml
- ['label~beta', 'label~^(?!.*closed).*']   # beta AND NOT closed
```

### Conditional Filtering

Use parameterized queries with conditional logic in caller:

```python
# Python code decides which query to run
if condition:
    result = execute_query("high_priority_items")
else:
    result = execute_query("normal_items")
```

### Aggregation Patterns

**Count results**:
```python
result = execute_query("open_tasks")
count = result['result_count']
print(f"Found {count} open tasks")
```

**Group by type** (execute multiple queries):
```python
epic_count = execute_query("open_epics")['result_count']
task_count = execute_query("open_tasks")['result_count']
subtask_count = execute_query("open_subtasks")['result_count']

print(f"Open: {epic_count} epics, {task_count} tasks, {subtask_count} subtasks")
```

### Edge Detection

**Leaf nodes** (no children):
```yaml
# Find tasks with no subtasks
- ['type=task']
# Then in code: filter where children array is empty
```

**Root nodes** (no parent):
```yaml
# Find epics with no parent
- ['type=epic']
# Then in code: filter where parent field is null
```

**Isolated tickets** (no relationships):
```yaml
# Find tickets with no parent, children, or dependencies
# Requires code to check all relationship fields are empty
```

### Ranking and Filtering

Use parameterized queries to support dynamic filtering:

```python
# Priority levels via parameter
params = '{"priority_pattern": "p[0-2]"}'  # High priority
result = execute_query("priority_filter", params=params)

params = '{"priority_pattern": "p[3-4]"}'  # Low priority
result = execute_query("priority_filter", params=params)
```

### Query Composition

Build complex queries from simple building blocks:

```yaml
# Building block queries
all_tasks:
  - ['type=task']

open_items:
  - ['label~open']

beta_items:
  - ['label~beta']

# Composed query (manually in code)
# Execute all_tasks, then filter result with open_items logic
```

### Recursive Traversal

Simulate recursive traversal with multiple stages:

```yaml
# Find all descendants (children, grandchildren, great-grandchildren)
- ['id=bees-ep1']
- ['children']         # Children
- ['children']         # Grandchildren
- ['children']         # Great-grandchildren
# Limited by number of stages (not truly recursive)
```

For true recursion, implement custom traversal logic outside query system.

---

For high-level overview and quick start, see main [README Query System
section](../README.md#query-system).
