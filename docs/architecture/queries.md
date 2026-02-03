# Query System Architecture

## Overview

The query system provides a powerful multi-stage pipeline for filtering and traversing tickets. Queries are composed of sequential stages, where each stage either filters tickets using search terms or traverses relationships using graph terms. Results from each stage are passed to the next, enabling complex queries through simple composition.

**Source files**: `src/query_parser.py`, `src/search_executor.py`, `src/graph_executor.py`, `src/pipeline.py`

## Query Parser Architecture

### Core Design

The Query Parser (`src/query_parser.py`) validates YAML query structures before execution, enforcing strict rules to ensure well-formed queries and providing clear error messages.

**Responsibilities**:
- Parse YAML query structure into list of stages
- Validate search terms (type=, id=, title~, label~, parent=)
- Validate graph terms (children, parent, up_dependencies, down_dependencies)
- Enforce stage purity (no mixing search and graph terms)
- Validate regex patterns are compilable

### Pipeline Execution Model

**Design Principles**:
- Stages evaluated sequentially in order
- Results from stage N passed to stage N+1
- Terms within a stage are ANDed together
- Results deduplicated after each stage
- Empty result set short-circuits pipeline

### Search Terms vs Graph Terms

**Search Terms** (filtering):
- `type=` - Exact match on ticket type (epic, task, subtask)
- `id=` - Exact match on ticket ID
- `title~` - Regex match on title field
- `label~` - Regex match on any label
- `parent=` - Exact match on parent field

**Graph Terms** (traversal):
- `parent` - Traverse to parent ticket
- `children` - Traverse to child tickets
- `up_dependencies` - Traverse to blocking dependencies
- `down_dependencies` - Traverse to blocked dependents

**Stage Purity Rule**: A stage can contain only search terms OR only graph terms, never both. This keeps execution logic clean and query semantics clear.

### Regex Features Supported

- Case-insensitive flags: `(?i)beta`
- Alternation (OR): `beta|alpha|preview`
- Negative lookahead (NOT): `^(?!.*closed).*`
- Character classes: `p[0-4]`
- Anchors: `^start`, `end$`

### AND/OR Semantics

**Within a stage** (AND logic):
- All terms must match for a ticket to pass
- Example: `[type=task, label~beta]` finds tasks AND labeled with beta

**Across stages** (sequential filtering):
- Stage 2 operates on stage 1 results
- Each stage narrows or traverses the result set
- Example: `[[type=epic], [children]]` finds epics, then gets their children

## Search Executor Architecture

The Search Executor (`src/search_executor.py`) implements in-memory filtering of tickets using search terms with AND semantics.

### Design Overview

**Purpose**: Execute search stages from query pipeline by filtering in-memory ticket data using exact match and regex patterns.

**Key Principle**: All search terms in a stage are ANDed together - a ticket must match ALL terms to be included in results.

**Integration**: Called by PipelineEvaluator when executing search stages (stages containing type=, id=, title~, label~, parent= terms).

### Architecture

**SearchExecutor Class**:
- Five filter methods (one per search term type)
- One execute method (orchestrates AND logic)
- Stateless design (no instance state)
- Pure functions (no side effects)

**Data Flow**:
- Input: `Dict[str, Dict[str, Any]]` - ticket_id → ticket data
- Output: `Set[str]` - set of matching ticket IDs
- In-memory operation (no disk I/O)

### Filter Methods

1. **filter_by_type(tickets, type_value)** - Exact match on `issue_type` field
2. **filter_by_id(tickets, id_value)** - Exact match on ticket ID
3. **filter_by_title_regex(tickets, regex_pattern)** - Regex match on `title` field
4. **filter_by_label_regex(tickets, regex_pattern)** - Regex match on ANY label in `labels` array
5. **filter_by_parent(tickets, parent_value)** - Exact match on `parent` field

### Execute Method AND Logic

**execute(tickets, search_terms)** orchestrates multi-term filtering:
- Applies each filter method for corresponding search term
- Intersects results (AND logic) across all filters
- Returns set of ticket IDs matching all terms

## Graph Executor Architecture

The Graph Executor (`src/graph_executor.py`) implements in-memory traversal of ticket relationships for the query pipeline.

### Design Overview

**Purpose**: Execute graph stages by traversing ticket relationships (parent, children, dependencies) without disk I/O.

**Key Principle**: Single-hop traversal only. Multi-hop queries use multiple graph stages in sequence.

### Relationship Traversal

**Single-value relationships**:
- `parent` - Returns the parent ticket ID (or empty if none)

**List-value relationships**:
- `children` - Returns all child ticket IDs
- `up_dependencies` - Returns all blocking dependency IDs
- `down_dependencies` - Returns all blocked dependent IDs

### Architecture Decisions

**Why single-hop only**:
- Keeps executor simple and predictable
- Multi-hop queries compose multiple graph stages
- Pipeline controls traversal depth explicitly

**Why no disk I/O**:
- All tickets pre-loaded by PipelineEvaluator
- Relationship data already parsed from YAML
- Executor just looks up fields in memory
- Orders of magnitude faster than disk reads

### Integration

**traverse(tickets, relationship_type)** method:
- Takes input ticket set from previous stage
- Looks up specified relationship field in each ticket
- Collects all relationship target IDs
- Returns set of reachable ticket IDs

**Graceful error handling**:
- Missing tickets return partial results (no failure)
- Malformed relationships logged and skipped
- Time complexity: O(n) where n is input ticket count

## Named Query System

Named queries allow storing and reusing query pipelines as YAML files in `.bees/queries/`.

### Components

**Query Storage** (`src/query_storage.py`):
- Manages persistent storage in `.bees/queries.yaml`
- Provides save/load/list operations
- All queries validated at registration time

**MCP Tools**:
- `add_named_query` - Register reusable query with validation
- `execute_query` - Run named query and return matching ticket IDs
- `execute_freeform_query` - One-step ad-hoc query execution without persistence

### Query Validation

Queries are validated at registration time to provide immediate feedback on structural errors:
- YAML syntax validation
- Stage structure validation
- Search term syntax validation
- Graph term validation
- Regex pattern compilation

### Multi-Hive Filtering

**Hive Parameter**: Both `execute_query` and `execute_freeform_query` accept optional `hive_names` parameter to filter results by hive.

**Filter Behavior**:
- `hive_names=None` - Include all tickets from all hives (default)
- `hive_names=["backend"]` - Only tickets from backend hive
- `hive_names=["backend", "frontend"]` - Tickets from multiple hives

**Implementation**: Filter applied at pipeline entry point before stage execution. Hive prefix extracted from ticket ID (e.g., `backend.bees-abc1` → `backend`).

### Named vs Freeform Queries

**Named queries**:
- Two-step process: register with `add_named_query`, execute with `execute_query`
- Persists to `.bees/queries.yaml` for reuse
- Suitable for production queries used repeatedly

**Freeform queries**:
- One-step process: `execute_freeform_query` validates and executes immediately
- No disk persistence
- Suitable for ad-hoc exploration and debugging

## Pipeline Execution Flow

1. **Load tickets once** - PipelineEvaluator loads all tickets into memory at initialization
2. **Apply hive filter** - If hive_names specified, filter initial set by hive prefix
3. **Execute stages sequentially** - For each stage:
   - Detect stage type (search or graph)
   - Route to appropriate executor (SearchExecutor or GraphExecutor)
   - Pass results to next stage
   - Short-circuit if results empty
4. **Deduplicate and return** - Return final set of matching ticket IDs

### Optimization Strategies

- **Batch loading**: Tickets loaded once and reused across all stages
- **Set-based deduplication**: Automatic via set data structure
- **Short-circuit evaluation**: Stop processing when any stage returns empty results
- **In-memory operations**: Zero disk I/O after initial load
