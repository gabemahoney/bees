# Query System Architecture

## Overview

The query system provides a powerful multi-stage pipeline for filtering and traversing tickets. Queries are composed of sequential stages, where each stage either filters tickets using search terms or traverses relationships using graph terms. Results from each stage are passed to the next, enabling complex queries through simple composition.

**Source files**: `src/query_parser.py`, `src/search_executor.py`, `src/graph_executor.py`, `src/pipeline.py`, `src/fast_parser.py`, `src/config.py`, `src/mcp_query_ops.py`

## Query Parser Architecture

### Core Design

The Query Parser (`src/query_parser.py`) validates dict-based query structures before execution, enforcing strict rules to ensure well-formed queries and providing clear error messages.

**Responsibilities**:
- Parse dict query structure (`{"stages": [...]}`) into validated stages
- Validate search terms (type=, id=, title~, tag~, parent=)
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
- `type=` - Exact match on ticket type (bee, t1, t2, etc.)
- `id=` - Exact match on ticket ID (e.g., `id=b.amx` or `id=t1.amx.12`)
- `title~` - Regex match on title field
- `tag~` - Regex match on any tag
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
- Example: `[type=t1, tag~beta]` finds t1 tickets AND tagged with beta

**Across stages** (sequential filtering):
- Stage 2 operates on stage 1 results
- Each stage narrows or traverses the result set
- Example: `[[type=bee], [children]]` finds bees, then gets their children

## Search Executor Architecture

The Search Executor (`src/search_executor.py`) implements in-memory filtering of tickets using search terms with AND semantics.

### Design Overview

**Purpose**: Execute search stages from query pipeline by filtering in-memory ticket data using exact match and regex patterns.

**Key Principle**: All search terms in a stage are ANDed together - a ticket must match ALL terms to be included in results.

**Integration**: Called by PipelineEvaluator when executing search stages (stages containing type=, id=, title~, tag~, parent= terms).

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
4. **filter_by_tag_regex(tickets, regex_pattern)** - Regex match on ANY tag in `tags` array
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

Named queries allow storing and reusing query pipelines in `~/.bees/config.json`. Queries are stored at two levels — global (top-level `queries` key) and repo scope (within a scope's `queries` key) — following the same scoped configuration model used for child_tiers and other settings. See `docs/architecture/configuration.md` (Named Queries Configuration section) for the detailed key structure, resolution order, and conflict detection rules.

### Storage Model

Named queries are persisted in config-backed storage within `~/.bees/config.json`:
- **Global queries**: Stored under the top-level `queries` dictionary. Accessible from any repo.
- **Repo-scoped queries**: Stored under a scope's `queries` dictionary. Accessible only from repos matching that scope pattern.

Repo scope queries shadow global queries of the same name. Validated queries are persisted as dicts with a `stages` key — `{"stages": [...]}`. The original YAML string is not retained.

### MCP Tools

**add_named_query** — Register a new named query for reuse.
- Parameters: `name` (str, required), `query_yaml` (str, required — YAML dict with a `stages` key, e.g. `"stages:\n  - [type=bee, status=pupa]"`), `scope` (str, "global" or "repo", default: "global")
- Returns on success: `{status: "success", query_name, scope, message}`
- Returns on error: `{status: "error", error_type, message}` (see Error Types below)

**execute_named_query** — Execute a previously registered named query.
- Parameters: `query_name` (str, required)
- Returns on success (no report): `{status: "success", query_name, result_count, ticket_ids}`
- Returns on success (with report): `{status: "success", query_name, result_count, tickets}` where `tickets` is a list of field dicts
- Report behavior is determined by the `report` key stored at `add_named_query` time
- Returns on error: `{status: "error", error_type, message}` with optional `available_queries` list for `query_not_found`
- Performs pre-flight hive integrity check before execution

**delete_named_query** — Delete a named query from config-backed storage.
- Parameters: `name` (str, required), `scope` (str, "global" or "repo", required)
- Returns on success: `{status: "success", query_name, scope, message}`
- Returns on error: `{status: "error", error_type, message}`
- Cleans up the `queries` key entirely if the last query at a scope level is removed

**list_named_queries** — List named queries from config-backed storage.
- Parameters: `all` (bool, default: False)
- When `all=False`: Returns queries accessible from current repo scope (matched repo-scoped queries + global queries)
- When `all=True`: Returns all queries across every scope and global
- Returns: `{status: "success", queries: [{name, definition, scope, repo_root}, ...], count}`

**execute_freeform_query** — One-step ad-hoc query execution without persistence.
- Parameters: `query_yaml` (str, required — YAML dict with a `stages` key and optional `report` key, e.g. `"stages:\n  - [type=bee, status=pupa]\nreport: [title, ticket_status]"`)
- Returns on success (no report): `{status: "success", result_count, ticket_ids, stages_executed}`
- Returns on success (with report): `{status: "success", result_count, tickets, stages_executed}` where `tickets` is a list of field dicts
- Performs pre-flight hive integrity check before execution

### Report Field Projection

The `report` parameter enables field projection on query results. When omitted, queries return a flat list of ticket IDs. When provided, queries return a list of ticket dicts containing only the requested fields.

**The `report` key**:
- Accepted by `execute_named_query` and `execute_freeform_query`
- Value is a list of field name strings, e.g. `["title", "ticket_status"]`
- An empty list is treated the same as omitting the parameter (returns `ticket_ids`)

**Response format**:
- Without `report`: response contains `ticket_ids` (list of ID strings)
- With `report`: response contains `tickets` (list of dicts, one per result ticket)

**Output field names**: The response always uses the external/output names, not internal model field names.

| Output name | Notes |
|---|---|
| `ticket_id` | Always included automatically. Silently stripped if caller supplies it in the list. |
| `ticket_type` | The ticket type (bee, t1, t2, etc.) |
| `ticket_status` | The ticket's current status |
| `title` | Ticket title |
| `tags` | List of tag strings |
| `parent` | Parent ticket ID, or null |
| `children` | List of child ticket IDs |
| `up_dependencies` | List of blocking dependency IDs |
| `down_dependencies` | List of blocked dependent IDs |
| `created_at` | ISO 8601 creation timestamp |
| `schema_version` | Internal schema version string |
| `guid` | Globally unique ticket identifier |

**Excluded fields**:
- `body` / `egg` — Excluded from projection because they can be arbitrarily large. Use `show_ticket` to fetch full ticket content.
- `hive` — Not stored in ticket data; cannot be projected.

### CLI Commands

**bees add-named-query --query-name NAME --query-yaml YAML [--scope {global,repo}]** — Register a named query. Scope defaults to "global". YAML must be a dict with a `stages` key and optional `report` key.

**bees execute-named-query --query-name NAME** — Execute a previously registered named query. Report behavior is determined by the stored query definition.

**bees delete-named-query --query-name NAME** — Delete a named query. Searches all scopes automatically.

**bees list-named-queries** — List accessible named queries from current repo scope and global.

**bees execute-freeform-query --query-yaml YAML** — Execute an ad-hoc YAML query without persistence. YAML must be a dict with a `stages` key and optional `report` key for field projection.

### Error Types

| Error Type | Condition |
|---|---|
| `query_not_found` | Query name does not exist at any accessible level (repo scope or global). Response includes `available_queries` list. |
| `query_out_of_scope` | Query exists but belongs to a different repo's scope and is not accessible from the caller's scope. |
| `query_name_conflict` | A query with the same name already exists. Returned by `add_named_query` when conflict detection finds a collision. Includes `conflict_level` and `conflict_location`. |
| `scope_not_found` | No registered scope in config matches the caller's repo root. Returned when `scope="repo"` but the repo has no scope entry. |
| `invalid_scope` | The scope parameter is not "global" or "repo". |

### Query Validation

Queries are validated at registration time to provide immediate feedback on structural errors:
- YAML syntax validation
- Stage structure validation
- Search term syntax validation
- Graph term validation
- Regex pattern compilation

### Multi-Hive Filtering

**Hive Parameter**: Both `execute_named_query` and `execute_freeform_query` accept optional `hive_names` parameter to filter results by hive.

**Filter Behavior**:
- `hive_names=None` - Include all tickets from all hives (default)
- `hive_names=["backend"]` - Only tickets from backend hive
- `hive_names=["backend", "frontend"]` - Tickets from multiple hives

**Implementation**: Filter applied at pipeline entry point before stage execution. Tickets filtered by hive membership (determined by ticket file location in hive directory).

### Named vs Freeform Queries

**Named queries**:
- Two-step process: register with `add_named_query`, execute with `execute_named_query`
- Persists to `~/.bees/config.json` (global or repo scope) for reuse
- Manageable via `delete_named_query` and `list_named_queries`
- Suitable for production queries used repeatedly

**Freeform queries**:
- One-step process: `execute_freeform_query` validates and executes immediately
- No persistence
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
